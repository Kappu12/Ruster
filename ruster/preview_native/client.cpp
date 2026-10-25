// Local, explicitly injected Rust IL2CPP prefab preview. GPL-3.0-or-later.
// No game offsets, code patches, driver, EAC disabling, or remote endpoints.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <winsvc.h>
#include <stdint.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <cwctype>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct Object; struct Class; struct Method; struct Type; struct Field; struct Image; struct Assembly;
struct Vec {float x,y,z;}; struct Quat {float x,y,z,w;};
HMODULE module;
std::wstring directory;
HWND window;
HHOOK hook;
DWORD windowThread;
HANDLE worker;
std::mutex pendingMutex;
std::vector<uint8_t> pending;
bool ready=false;
std::atomic<bool> stopping{false}, stopped{false};
uint64_t applied=0;
constexpr UINT PREVIEW_MESSAGE=WM_APP+0x531;

bool eacName(std::wstring name) {
    std::transform(name.begin(),name.end(),name.begin(),::towlower);
    auto pos=name.find_last_of(L"/\\");if(pos!=std::wstring::npos)name=name.substr(pos+1);
    return name.find(L"easyanticheat")!=std::wstring::npos || name.rfind(L"eac_",0)==0
        || name.rfind(L"eac.",0)==0 || name.rfind(L"eac-",0)==0
        || name.rfind(L"eacclient",0)==0 || name.rfind(L"eacserver",0)==0;
}

bool eacOff() {
    // Recheck within the DLL before installing a callback, and during preview.
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,GetCurrentProcessId());
    if(snap==INVALID_HANDLE_VALUE)return false;
    MODULEENTRY32W item{};item.dwSize=sizeof(item);
    bool ok=Module32FirstW(snap,&item)!=FALSE;
    if(ok)do {if(eacName(item.szModule)){ok=false;break;}}while(Module32NextW(snap,&item));
    CloseHandle(snap);if(!ok)return false;
    snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);if(snap==INVALID_HANDLE_VALUE)return false;
    PROCESSENTRY32W process{};process.dwSize=sizeof(process);ok=Process32FirstW(snap,&process)!=FALSE;
    if(ok)do {if(eacName(process.szExeFile)){ok=false;break;}}while(Process32NextW(snap,&process));
    CloseHandle(snap);if(!ok)return false;
    SC_HANDLE scm=OpenSCManagerW(nullptr,nullptr,SC_MANAGER_ENUMERATE_SERVICE);
    if(!scm)return false;
    std::vector<uint8_t> buffer(256*1024);DWORD needed=0,count=0,resume=0;
    ok=EnumServicesStatusExW(scm,SC_ENUM_PROCESS_INFO,SERVICE_WIN32|SERVICE_DRIVER,SERVICE_STATE_ALL,
        buffer.data(),DWORD(buffer.size()),&needed,&count,&resume,nullptr)!=FALSE;
    if(ok){auto entries=reinterpret_cast<ENUM_SERVICE_STATUS_PROCESSW*>(buffer.data());
        for(DWORD i=0;i<count;i++)if(entries[i].ServiceStatusProcess.dwCurrentState!=SERVICE_STOPPED
            && (eacName(entries[i].lpServiceName)||eacName(entries[i].lpDisplayName)))ok=false;
    }
    CloseServiceHandle(scm);return ok;
}

std::wstring file(const wchar_t* name){return directory+L"/"+name;}
bool exists(const wchar_t* name){return GetFileAttributesW(file(name).c_str())!=INVALID_FILE_ATTRIBUTES;}
void status(const char* state,const std::string& message) {
    auto path=file(L"client.status");auto temp=path+L".tmp";
    HANDLE out=CreateFileW(temp.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(out==INVALID_HANDLE_VALUE)return;
    std::string value=std::string(state)+"\n"+message+"\n";DWORD written;
    WriteFile(out,value.data(),DWORD(value.size()),&written,nullptr);CloseHandle(out);
    MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}
std::string readText(const wchar_t* name){std::ifstream f{std::filesystem::path(file(name))};return {std::istreambuf_iterator<char>(f),{}};}

// Use the game's public IL2CPP reflection ABI. Signature matching tolerates
// renamed game types, while ambiguous/missing methods fail without patching.
struct Api {
    void*(*domain_get)();
    const Assembly**(*domain_get_assemblies)(void*,size_t*);
    const Image*(*assembly_get_image)(const Assembly*);
    size_t(*image_get_class_count)(const Image*);
    Class*(*image_get_class)(const Image*,size_t);
    const char*(*class_get_name)(Class*);
    const char*(*class_get_namespace)(Class*);
    const Method*(*class_get_methods)(Class*,void**);
    Field*(*class_get_fields)(Class*,void**);
    const Type*(*field_get_type)(Field*);
    int(*field_get_flags)(Field*);
    void(*field_static_get_value)(Field*,void*);
    const char*(*method_get_name)(const Method*);
    uint32_t(*method_get_param_count)(const Method*);
    const Type*(*method_get_param)(const Method*,uint32_t);
    const Type*(*method_get_return_type)(const Method*);
    uint32_t(*method_get_flags)(const Method*,uint32_t*);
    char*(*type_get_name)(const Type*);
    void(*free_)(void*);
    Object*(*runtime_invoke)(const Method*,void*,void**,Object**);
    const Type*(*class_get_type)(Class*);
    Object*(*type_get_object)(const Type*);
    void*(*object_unbox)(Object*);
    uintptr_t(*array_length)(Object*);
    Object*(*string_new)(const char*);
    const wchar_t*(*string_chars)(Object*);
    int(*string_length)(Object*);
    void*(*thread_current)();
    uint32_t(*gchandle_new)(Object*,bool);
    Object*(*gchandle_get_target)(uint32_t);
    void(*gchandle_free)(uint32_t);
    void load() {
        HMODULE game=GetModuleHandleW(L"GameAssembly.dll");if(!game)throw std::runtime_error("GameAssembly.dll is not loaded");
#define API(member,name) member=reinterpret_cast<decltype(member)>(GetProcAddress(game,"il2cpp_" name)); if(!member)throw std::runtime_error("Missing IL2CPP export: " name)
        API(domain_get,"domain_get");API(domain_get_assemblies,"domain_get_assemblies");
        API(assembly_get_image,"assembly_get_image");API(image_get_class_count,"image_get_class_count");
        API(image_get_class,"image_get_class");API(class_get_name,"class_get_name");API(class_get_namespace,"class_get_namespace");
        API(class_get_methods,"class_get_methods");API(class_get_fields,"class_get_fields");
        API(field_get_type,"field_get_type");API(field_get_flags,"field_get_flags");API(field_static_get_value,"field_static_get_value");
        API(method_get_name,"method_get_name");API(method_get_param_count,"method_get_param_count");
        API(method_get_param,"method_get_param");API(method_get_return_type,"method_get_return_type");API(method_get_flags,"method_get_flags");
        API(type_get_name,"type_get_name");API(free_,"free");API(runtime_invoke,"runtime_invoke");API(string_new,"string_new");
        API(class_get_type,"class_get_type");API(type_get_object,"type_get_object");API(object_unbox,"object_unbox");API(array_length,"array_length");
        API(string_chars,"string_chars");API(string_length,"string_length");API(thread_current,"thread_current");
        API(gchandle_new,"gchandle_new");API(gchandle_get_target,"gchandle_get_target");API(gchandle_free,"gchandle_free");
#undef API
    }
    std::string name(const Type* type){char* p=type_get_name(type);if(!p)return {};std::string s=p;free_(p);return s;}
    std::string name(Class* type){std::string ns=class_get_namespace(type);return ns.empty()?class_get_name(type):ns+"."+class_get_name(type);}
    Object* call(const Method* method,void* self,void** args=nullptr){
        if(!method)throw std::runtime_error("A required game method is unavailable");
        Object* error=nullptr;Object* value=runtime_invoke(method,self,args,&error);
        if(error)throw std::runtime_error("Rust rejected a preview operation; this asset may need loading through a map first");
        return value;
    }
    std::string text(Object* s){
        if(!s)return {};int n=string_length(s);if(n<0||n>8192)return {};
        int bytes=WideCharToMultiByte(CP_UTF8,0,string_chars(s),n,nullptr,0,nullptr,nullptr);
        std::string out(bytes,0);WideCharToMultiByte(CP_UTF8,0,string_chars(s),n,out.data(),bytes,nullptr,nullptr);return out;
    }
}api;

const Method *createPrefab,*getTransform,*setPosition,*setRotation,*setScale,*destroyObject;
const Method *findPrefab,*getComponent,*findObjects,*getName,*getPosition,*getScene,*sceneValid,*arrayGet;
Object *gameObjectType=nullptr,*networkableType=nullptr;
Object* manager=nullptr;
std::vector<Field*> worldUrls;
bool signature(const Method* method,const char* result,std::initializer_list<const char*> params) {
    if(api.method_get_param_count(method)!=params.size()||api.name(api.method_get_return_type(method))!=result)return false;
    uint32_t i=0;for(auto p:params)if(api.name(api.method_get_param(method,i++))!=p)return false;
    return true;
}

void initialize() {
    api.load();if(!api.thread_current())throw std::runtime_error("The game window is not on an IL2CPP main thread");
    size_t count=0;auto assemblies=api.domain_get_assemblies(api.domain_get(),&count);
    int factories=0;
    for(size_t a=0;a<count;a++) {
        auto image=api.assembly_get_image(assemblies[a]);size_t total=api.image_get_class_count(image);
        for(size_t c=0;c<total;c++) {
            Class* klass=api.image_get_class(image,c);if(!klass)continue;
            std::string type=api.name(klass);void* it=nullptr;bool hasWorld=false;
            if(type=="UnityEngine.GameObject")gameObjectType=api.type_get_object(api.class_get_type(klass));
            if(type=="BaseNetworkable")networkableType=api.type_get_object(api.class_get_type(klass));
            std::vector<Field*> strings;
            while(Field* f=api.class_get_fields(klass,&it))if(api.field_get_flags(f)&0x10) {
                auto fieldType=api.name(api.field_get_type(f));
                if(fieldType=="WorldSerialization")hasWorld=true;
                if(fieldType=="System.String")strings.push_back(f);
            }
            if(hasWorld)worldUrls.insert(worldUrls.end(),strings.begin(),strings.end());
            it=nullptr;
            while(const Method* m=api.class_get_methods(klass,&it)) {
                std::string name=api.method_get_name(m);
                if(type=="UnityEngine.GameObject"&&name=="get_transform"&&api.method_get_param_count(m)==0)getTransform=m;
                if(type=="UnityEngine.GameObject"&&name=="get_scene"&&api.method_get_param_count(m)==0)getScene=m;
                if(type=="UnityEngine.GameObject"&&name=="GetComponent"&&signature(m,"UnityEngine.Component",{"System.Type"}))getComponent=m;
                if(type=="UnityEngine.Object"&&name=="get_name"&&api.method_get_param_count(m)==0)getName=m;
                if(type=="UnityEngine.Transform"&&name=="get_position"&&api.method_get_param_count(m)==0)getPosition=m;
                if(type=="UnityEngine.SceneManagement.Scene"&&name=="IsValid"&&api.method_get_param_count(m)==0)sceneValid=m;
                if(type=="UnityEngine.Resources"&&name=="FindObjectsOfTypeAll"&&signature(m,"UnityEngine.Object[]",{"System.Type"}))findObjects=m;
                if(type=="System.Array"&&name=="GetValue"&&signature(m,"System.Object",{"System.Int32"}))arrayGet=m;
                if(type=="UnityEngine.Transform"&&api.method_get_param_count(m)==1) {
                    if(name=="set_position")setPosition=m;
                    if(name=="set_rotation")setRotation=m;
                    if(name=="set_localScale")setScale=m;
                }
                if(type=="UnityEngine.Object"&&name=="Destroy"&&signature(m,"System.Void",{"UnityEngine.Object"}))destroyObject=m;
                if(!signature(m,"UnityEngine.GameObject",{"System.String","UnityEngine.Vector3","UnityEngine.Quaternion","UnityEngine.Vector3","System.Boolean"}))continue;
                if(api.method_get_flags(m,nullptr)&0x10)continue;
                void* fields=nullptr;Object* candidate=nullptr;int candidates=0;
                while(Field* f=api.class_get_fields(klass,&fields))if((api.field_get_flags(f)&0x10)&&!(api.field_get_flags(f)&0x40)
                        &&api.name(api.field_get_type(f))==type) {
                    Object* value=nullptr;api.field_static_get_value(f,&value);
                    if(value&&value!=candidate){candidate=value;candidates++;}
                }
                if(candidates==1){
                    createPrefab=m;manager=candidate;factories++;
                    void* methods=nullptr;int finders=0;
                    while(const Method* f=api.class_get_methods(klass,&methods))if(signature(f,"UnityEngine.GameObject",{"System.String"})){
                        findPrefab=f;finders++;
                    }
                    if(finders!=1)throw std::runtime_error("Ambiguous Rust prefab lookup API");
                }
            }
        }
    }
    if(factories!=1||!manager||!getTransform||!setPosition||!setRotation||!setScale||!destroyObject||worldUrls.empty()
            ||!findPrefab||!getComponent||!findObjects||!getName||!getPosition||!getScene||!sceneValid||!arrayGet||!gameObjectType||!networkableType)
        throw std::runtime_error("This Rust build has no unambiguous preview API; no game offsets or fallback patches were applied");
    ready=true;
}

bool inPreviewWorld() {
    if(!exists(L"client.connected"))return false;
    std::string expected=readText(L"map.url");
    if(expected.empty())return false;
    for(auto field:worldUrls){Object* value=nullptr;api.field_static_get_value(field,&value);if(api.text(value)==expected)return true;}
    return false;
}

struct Placement {uint64_t key;uint32_t uid;std::string path;Vec pos;Quat rot;Vec scale;};
struct Instance {uint32_t handle;uint32_t uid;};
std::map<uint64_t,Instance> objects;
bool baseline=false;
template<typename T>T take(const std::vector<uint8_t>& data,size_t& offset) {
    if(offset+sizeof(T)>data.size())throw std::runtime_error("Truncated preview snapshot");
    T result;memcpy(&result,data.data()+offset,sizeof(T));offset+=sizeof(T);return result;
}
std::vector<Placement> decode(const std::vector<uint8_t>& data,uint64_t& revision) {
    if(data.size()<20||data.size()>16*1024*1024||memcmp(data.data(),"RUSLIVE1",8))throw std::runtime_error("Invalid preview snapshot");
    size_t offset=8;revision=take<uint64_t>(data,offset);uint32_t count=take<uint32_t>(data,offset);
    if(count>2000)throw std::runtime_error("Too many preview placements");std::vector<Placement> rows;std::map<uint64_t,bool> keys;
    for(uint32_t i=0;i<count;i++) {
        Placement p;p.key=take<uint64_t>(data,offset);p.uid=take<uint32_t>(data,offset);auto length=take<uint32_t>(data,offset);
        if(!p.key||!p.uid||keys.count(p.key)||length>4096||offset+length>data.size())throw std::runtime_error("Invalid preview placement");
        keys[p.key]=true;p.path=std::string(reinterpret_cast<const char*>(data.data()+offset),length);offset+=length;
        if(p.path.rfind("assets/",0)!=0||p.path.find("..")!=std::string::npos||p.path.find('\0')!=std::string::npos
                ||p.path.find('\\')!=std::string::npos||p.path.size()<7||p.path.substr(p.path.size()-7)!=".prefab")throw std::runtime_error("Invalid prefab path");
        p.pos=take<Vec>(data,offset);p.rot=take<Quat>(data,offset);p.scale=take<Vec>(data,offset);
        float values[10];memcpy(values,&p.pos,12);memcpy(values+3,&p.rot,16);memcpy(values+7,&p.scale,12);
        for(float v:values)if(!std::isfinite(v)||fabs(v)>=1e7)throw std::runtime_error("Invalid preview transform");
        float norm=p.rot.x*p.rot.x+p.rot.y*p.rot.y+p.rot.z*p.rot.z+p.rot.w*p.rot.w;
        if(fabs(norm-1)>.001||fabs(p.scale.x)<1e-6||fabs(p.scale.y)<1e-6||fabs(p.scale.z)<1e-6)throw std::runtime_error("Invalid scale or rotation");
        rows.push_back(p);
    }
    if(offset!=data.size())throw std::runtime_error("Unexpected snapshot data");return rows;
}
void remove(Instance instance) {
    Object* value=api.gchandle_get_target(instance.handle);if(value){void* args[]={value};api.call(destroyObject,nullptr,args);}api.gchandle_free(instance.handle);
}
void clear() {for(auto& entry:objects)remove(entry.second);objects.clear();applied=0;}
bool isNetworked(Object* object) {void* args[]={networkableType};return api.call(getComponent,object,args)!=nullptr;}
void claimInitial() {
    std::ifstream input(std::filesystem::path(file(L"initial.bin")),std::ios::binary|std::ios::ate);
    if(!input||input.tellg()>16*1024*1024)throw std::runtime_error("Initial preview snapshot is unavailable");
    auto length=input.tellg();std::vector<uint8_t> data(static_cast<size_t>(length));input.seekg(0);
    input.read(reinterpret_cast<char*>(data.data()),length);uint64_t revision;auto rows=decode(data,revision);
    void* args[]={gameObjectType};Object* all=api.call(findObjects,nullptr,args);auto count=api.array_length(all);
    if(count>1000000)throw std::runtime_error("Game object lookup exceeds preview limits");
    std::map<std::string,std::vector<Object*>> byPath;
    for(auto& p:rows)byPath[p.path];
    for(uintptr_t i=0;i<count;i++) {
        int index=int(i);void* indexArgs[]={&index};Object* obj=api.call(arrayGet,all,indexArgs);
        auto name=api.text(api.call(getName,obj));auto found=byPath.find(name);if(found==byPath.end())continue;
        Object* scene=api.call(getScene,obj);Object* valid=api.call(sceneValid,api.object_unbox(scene));
        if(valid&&*static_cast<bool*>(api.object_unbox(valid)))found->second.push_back(obj);
    }
    std::map<uint64_t,Instance> claimed;
    try {
        for(auto& p:rows) {
            Object* match=nullptr;auto& candidates=byPath[p.path];
            for(auto it=candidates.begin();it!=candidates.end();++it){
                Object* transform=api.call(getTransform,*it);Object* boxed=api.call(getPosition,transform);
                Vec pos=*static_cast<Vec*>(api.object_unbox(boxed));
                if(fabs(pos.x-p.pos.x)<.005&&fabs(pos.y-p.pos.y)<.005&&fabs(pos.z-p.pos.z)<.005){match=*it;candidates.erase(it);break;}
            }
            if(!match)throw std::runtime_error("Waiting for the initial map object: "+p.path);
            if(!isNetworked(match))claimed[p.key]={api.gchandle_new(match,false),p.uid};
        }
    }catch(...){for(auto& entry:claimed)api.gchandle_free(entry.second.handle);throw;}
    objects.swap(claimed);baseline=true;
}

LRESULT CALLBACK onMessage(int code,WPARAM wp,LPARAM lp) {
    if(code>=0&&wp==PM_REMOVE&&reinterpret_cast<MSG*>(lp)->message==PREVIEW_MESSAGE) {
        try {
            if(GetCurrentThreadId()!=windowThread)throw std::runtime_error("Wrong Unity window thread");
            if(!ready)initialize();
            if(stopping){clear();stopped=true;status("STOPPED","Preview stopped. Restart Rust before joining EAC servers.");}
            else if(!inPreviewWorld()){
                // Let Rust unload its own world on disconnect. Do not destroy
                // new-scene objects through stale Unity references.
                for(auto& entry:objects)api.gchandle_free(entry.second.handle);
                objects.clear();applied=0;baseline=false;
                status("WAITING","Join the local preview server using Copy IP.");
            }
            else {
                if(!baseline)claimInitial();
                std::vector<uint8_t> data;{std::lock_guard<std::mutex> lock(pendingMutex);data=pending;}
                if(!data.empty()) {
                    uint64_t revision;auto rows=decode(data,revision);
                    if(revision!=applied) {
                        std::map<uint64_t,bool> present;
                        // The transaction is bounded to 2000 placements. A user
                        // edit snapshot is replaced only after complete parsing.
                        for(auto& p:rows) {
                            Object* path=api.string_new(p.path.c_str());void* lookup[]={path};
                            Object* prefab=api.call(findPrefab,manager,lookup);
                            if(!prefab)throw std::runtime_error("Rust could not load "+p.path+". Restart preview with this asset in the initial scene.");
                            if(isNetworked(prefab))continue; // Native network replication owns these.
                            present[p.key]=true;auto found=objects.find(p.key);
                            if(found!=objects.end()&&found->second.uid!=p.uid){remove(found->second);objects.erase(found);found=objects.end();}
                            Object* obj=nullptr;
                            if(found==objects.end()) {
                                bool active=true;void* args[]={path,&p.pos,&p.rot,&p.scale,&active};
                                obj=api.call(createPrefab,manager,args);
                                if(!obj)throw std::runtime_error("Rust could not load "+p.path+". Load this asset in the preview map first.");
                                objects[p.key]={api.gchandle_new(obj,false),p.uid};
                            }else obj=api.gchandle_get_target(found->second.handle);
                            Object* transform=api.call(getTransform,obj);void* pos[]={&p.pos};void* rot[]={&p.rot};void* scale[]={&p.scale};
                            api.call(setPosition,transform,pos);api.call(setRotation,transform,rot);api.call(setScale,transform,scale);
                        }
                        for(auto it=objects.begin();it!=objects.end();)if(!present.count(it->first)){remove(it->second);it=objects.erase(it);}else ++it;
                        applied=revision;status("READY","Live scene revision "+std::to_string(revision)+" applied ("+std::to_string(rows.size())+" placements).");
                    }
                }
            }
        }catch(const std::exception& error){status("ERROR",error.what());}
    }
    return CallNextHookEx(hook,code,wp,lp);
}
BOOL CALLBACK findWindow(HWND hwnd,LPARAM) {
    DWORD pid;DWORD thread=GetWindowThreadProcessId(hwnd,&pid);wchar_t name[256];
    if(pid==GetCurrentProcessId()&&GetClassNameW(hwnd,name,256)&&std::wstring(name)==L"UnityWndClass"){
        window=hwnd;windowThread=thread;return FALSE;
    }return TRUE;
}
DWORD WINAPI run(void*) {
    if(!eacOff()){status("BLOCKED","EAC state failed verification inside the preview module.");return 1;}
    EnumWindows(findWindow,0);
    if(!window){status("ERROR","Rust has no Unity game window yet.");return 2;}
    hook=SetWindowsHookExW(WH_GETMESSAGE,onMessage,module,windowThread);
    if(!hook){status("ERROR","Could not register the local main-thread preview callback.");return 3;}
    status("STARTING","Waiting for the Unity main thread and local preview map.");
    while(exists(L"active.flag")) {
        if(!eacOff()){status("BLOCKED","EAC became active or unreadable. Preview has stopped.");UnhookWindowsHookEx(hook);return 4;}
        std::ifstream input(std::filesystem::path(file(L"scene.bin")),std::ios::binary|std::ios::ate);
        if(input){auto length=input.tellg();if(length>=20&&length<=16*1024*1024){
            std::vector<uint8_t> value(static_cast<size_t>(length));input.seekg(0);input.read(reinterpret_cast<char*>(value.data()),length);
            if(input){std::lock_guard<std::mutex> lock(pendingMutex);pending.swap(value);}
        }}
        PostMessageW(window,PREVIEW_MESSAGE,0,0);Sleep(250);
    }
    stopping=true;PostMessageW(window,PREVIEW_MESSAGE,0,0);
    for(int i=0;i<40&&!stopped;i++)Sleep(50);
    UnhookWindowsHookEx(hook);return 0;
}
}

extern "C" __declspec(dllexport) DWORD WINAPI RusterStart(void* argument) {
    if(worker) {
        if(WaitForSingleObject(worker,0)!=WAIT_OBJECT_0)return 5;
        CloseHandle(worker);worker=nullptr;
    }
    if(!argument||!eacOff())return 1;
    stopping=false;stopped=false;baseline=false;applied=0;
    directory=static_cast<const wchar_t*>(argument);
    if(directory.size()>30000||!exists(L"active.flag")||!exists(L"scene.bin")||!exists(L"map.url"))return 2;
    worker=CreateThread(nullptr,0,run,nullptr,0,nullptr);return worker?0:3;
}
BOOL WINAPI DllMain(HINSTANCE self,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH){module=self;DisableThreadLibraryCalls(self);}return TRUE;
}

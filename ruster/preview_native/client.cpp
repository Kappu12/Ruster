// Local, explicitly injected Rust IL2CPP prefab preview. GPL-3.0-or-later.
// No game offsets, code patches, driver, EAC disabling, or remote endpoints.
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <tlhelp32.h>
#include <winsvc.h>
#include <stdint.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
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
// Unity 6's Il2CppGCHandle is void*, not the uint32_t used by older runtimes.
// Keep the opaque value intact through creation, storage, lookup and release.
using GCHandle=void*;
static_assert(sizeof(GCHandle)==8,"Preview requires the Windows x64 IL2CPP ABI");
struct Vec {float x,y,z;}; struct Quat {float x,y,z,w;};
HMODULE module;
std::wstring directory;
HWND window;
HHOOK hook;
DWORD windowThread;
HANDLE worker;
std::mutex pendingMutex;
std::mutex statusMutex;
std::string lastStatus;
std::vector<uint8_t> pending;
bool ready=false;
std::atomic<bool> initializationFailed{false};
std::atomic<bool> stopping{false}, stopped{false};
std::atomic_flag callbackActive=ATOMIC_FLAG_INIT;
uint64_t applied=0;
uint64_t attempted=0;
size_t appliedCount=0;
constexpr UINT PREVIEW_MESSAGE=WM_APP+0x531;

bool eacName(std::wstring name) {
    std::transform(name.begin(),name.end(),name.begin(),::towlower);
    auto pos=name.find_last_of(L"/\\");if(pos!=std::wstring::npos)name=name.substr(pos+1);
    return name.find(L"easyanticheat")!=std::wstring::npos || name.rfind(L"eac_",0)==0
        || name.rfind(L"eac.",0)==0 || name.rfind(L"eac-",0)==0
        || name.rfind(L"eacclient",0)==0 || name.rfind(L"eacserver",0)==0
        || name.rfind(L"eacdriver",0)==0 || name.rfind(L"eaclauncher",0)==0
        || name.rfind(L"eacservice",0)==0 || name==L"start_protected_game.exe";
}

bool eacOff() {
    // Recheck within the DLL before installing a callback, and during preview.
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,GetCurrentProcessId());
    if(snap==INVALID_HANDLE_VALUE)return false;
    MODULEENTRY32W item{};item.dwSize=sizeof(item);
    bool ok=Module32FirstW(snap,&item)!=FALSE;
    if(ok)do {if(eacName(item.szModule)){ok=false;break;}}while(Module32NextW(snap,&item));
    if(ok&&GetLastError()!=ERROR_NO_MORE_FILES)ok=false;
    CloseHandle(snap);if(!ok)return false;
    snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);if(snap==INVALID_HANDLE_VALUE)return false;
    PROCESSENTRY32W process{};process.dwSize=sizeof(process);ok=Process32FirstW(snap,&process)!=FALSE;
    if(ok)do {if(eacName(process.szExeFile)){ok=false;break;}}while(Process32NextW(snap,&process));
    if(ok&&GetLastError()!=ERROR_NO_MORE_FILES)ok=false;
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
bool serverFresh() {
    WIN32_FILE_ATTRIBUTE_DATA data{};FILETIME now;
    if(!GetFileAttributesExW(file(L"server.ready").c_str(),GetFileExInfoStandard,&data)
            ||data.nFileSizeHigh||data.nFileSizeLow>4096)return false;
    GetSystemTimeAsFileTime(&now);
    ULARGE_INTEGER current{},written{};current.LowPart=now.dwLowDateTime;current.HighPart=now.dwHighDateTime;
    written.LowPart=data.ftLastWriteTime.dwLowDateTime;written.HighPart=data.ftLastWriteTime.dwHighDateTime;
    auto age=int64_t(current.QuadPart)-int64_t(written.QuadPart);
    return age>=-20000000&&age<=150000000;
}
void status(const char* state,const std::string& message) noexcept {try {
    std::lock_guard<std::mutex> lock(statusMutex);
    std::string value=std::string(state)+"\n"+message+"\n";
    if(value==lastStatus)return;
    auto path=file(L"client.status");auto temp=path+L".tmp";
    HANDLE out=CreateFileW(temp.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(out==INVALID_HANDLE_VALUE)return;
    DWORD written=0;
    bool saved=WriteFile(out,value.data(),DWORD(value.size()),&written,nullptr)&&written==value.size();CloseHandle(out);
    if(!saved)return;
    if(!MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return;
    lastStatus=value;
    // Keep transitions after the status file changes, so a later state cannot
    // erase the reason an otherwise running session paused or stopped.
    WIN32_FILE_ATTRIBUTE_DATA info{};auto log=file(L"client.log");
    bool rotate=GetFileAttributesExW(log.c_str(),GetFileExInfoStandard,&info)
        &&(info.nFileSizeHigh||info.nFileSizeLow>1024*1024);
    out=CreateFileW(log.c_str(),rotate?GENERIC_WRITE:FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
        nullptr,rotate?CREATE_ALWAYS:OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(out!=INVALID_HANDLE_VALUE){
        SYSTEMTIME now;GetSystemTime(&now);char stamp[32];
        std::snprintf(stamp,sizeof(stamp),"%04u-%02u-%02uT%02u:%02u:%02uZ ",
            unsigned(now.wYear),unsigned(now.wMonth),unsigned(now.wDay),unsigned(now.wHour),unsigned(now.wMinute),unsigned(now.wSecond));
        auto line=std::string(stamp)+state+" "+message+"\r\n";
        WriteFile(out,line.data(),DWORD(line.size()),&written,nullptr);CloseHandle(out);
    }
}catch(...) {}}
struct PreviewFileUnavailable:std::runtime_error {using std::runtime_error::runtime_error;};
std::vector<uint8_t> readBytes(const wchar_t* name,size_t maximum) {
    // CRT ifstreams omit FILE_SHARE_DELETE on Windows and can make an atomic
    // editor snapshot replacement fail while the game is reading its old file.
    struct File {HANDLE handle;~File(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}} input{
        CreateFileW(file(name).c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
            nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr)};
    if(input.handle==INVALID_HANDLE_VALUE)throw PreviewFileUnavailable("Preview file is unavailable (Windows error "+std::to_string(GetLastError())+")");
    LARGE_INTEGER length{};
    if(!GetFileSizeEx(input.handle,&length))throw PreviewFileUnavailable("Cannot read preview file size");
    if(length.QuadPart<0||uint64_t(length.QuadPart)>maximum)throw std::runtime_error("Preview file exceeds size limits");
    std::vector<uint8_t> data(static_cast<size_t>(length.QuadPart));DWORD read=0;
    if(length.QuadPart&&(!ReadFile(input.handle,data.data(),DWORD(data.size()),&read,nullptr)||read!=data.size()))throw PreviewFileUnavailable("Incomplete preview file read");
    return data;
}
std::string readText(const wchar_t* name){auto data=readBytes(name,4096);return {data.begin(),data.end()};}
bool queueSnapshot() {
    std::vector<uint8_t> value;std::string waiting;
    if(!serverFresh())waiting="Waiting for a fresh local server heartbeat; edits are paused and will resume automatically.";
    else try{value=readBytes(L"scene.bin",16*1024*1024);}
        catch(const PreviewFileUnavailable& error){waiting=std::string("Waiting for the editor snapshot: ")+error.what();}
    if(!waiting.empty()){
        {std::lock_guard<std::mutex> lock(pendingMutex);pending.clear();}
        status("WAITING",waiting);return false;
    }
    if(value.size()<20)throw std::runtime_error("Incomplete preview snapshot");
    {std::lock_guard<std::mutex> lock(pendingMutex);pending.swap(value);}
    return true;
}

template<typename T>T take(const std::vector<uint8_t>& data,size_t& offset) {
    if(offset+sizeof(T)>data.size())throw std::runtime_error("Truncated preview data");
    T result;memcpy(&result,data.data()+offset,sizeof(T));offset+=sizeof(T);return result;
}
struct Peer {std::string token,url;uint32_t server,port;int64_t timestamp;};
Peer decodePeer(const std::vector<uint8_t>& data) {
    if(data.size()<60||data.size()>2108||memcmp(data.data(),"RUSPEER2",8))throw std::runtime_error("Invalid local connection proof");
    Peer peer;const char* hex="0123456789abcdef";
    for(size_t i=8;i<40;i++){peer.token+=hex[data[i]>>4];peer.token+=hex[data[i]&15];}
    size_t offset=40;peer.server=take<uint32_t>(data,offset);peer.port=take<uint32_t>(data,offset);
    peer.timestamp=take<int64_t>(data,offset);auto length=take<uint32_t>(data,offset);
    if(!peer.server||!peer.port||peer.port>65535||peer.timestamp<=0||!length||length>2048||offset+length!=data.size())
        throw std::runtime_error("Invalid local connection identity");
    peer.url=std::string(data.begin()+offset,data.end());
    if(peer.url.rfind("http://127.0.0.1:",0)!=0||peer.url.find('\0')!=std::string::npos)
        throw std::runtime_error("Invalid local map URL");
    return peer;
}
uint32_t decimal(const std::string& text) {
    if(text.empty()||text.size()>10||!std::all_of(text.begin(),text.end(),[](unsigned char c){return c>='0'&&c<='9';}))
        throw std::runtime_error("Invalid preview server PID");
    auto value=std::stoull(text);if(!value||value>UINT32_MAX)throw std::runtime_error("Invalid preview server PID");return uint32_t(value);
}
bool matchingPeer(const Peer& peer,const std::string& token,uint32_t pid,const std::string& url,int64_t now) {
    return token.size()==64&&peer.token==token&&peer.server==pid&&peer.url==url&&peer.timestamp>=now-1500&&peer.timestamp<=now+2000;
}
bool ownsUdpFamily(uint32_t port,ULONG family) {
    DWORD size=0;
    if(GetExtendedUdpTable(nullptr,&size,FALSE,family,UDP_TABLE_OWNER_PID,0)!=ERROR_INSUFFICIENT_BUFFER)return false;
    if(size<sizeof(DWORD)||size>4*1024*1024)return false;
    std::vector<uint8_t> data(size);
    if(GetExtendedUdpTable(data.data(),&size,FALSE,family,UDP_TABLE_OWNER_PID,0)!=NO_ERROR)return false;
    if(family==AF_INET6) {
        auto table=reinterpret_cast<MIB_UDP6TABLE_OWNER_PID*>(data.data());
        if(table->dwNumEntries>(data.size()-offsetof(MIB_UDP6TABLE_OWNER_PID,table))/sizeof(MIB_UDP6ROW_OWNER_PID))return false;
        for(DWORD i=0;i<table->dwNumEntries;i++) {
            auto& row=table->table[i];auto addr=row.ucLocalAddr;
            bool wildcard=std::all_of(addr,addr+16,[](uint8_t c){return c==0;});
            bool loopback=std::all_of(addr,addr+15,[](uint8_t c){return c==0;})&&addr[15]==1;
            bool mapped=std::all_of(addr,addr+10,[](uint8_t c){return c==0;})&&addr[10]==255&&addr[11]==255&&addr[12]==127;
            if(row.dwOwningPid==GetCurrentProcessId()&&ntohs(uint16_t(row.dwLocalPort))==port&&(wildcard||loopback||mapped))return true;
        }
        return false;
    }
    auto table=reinterpret_cast<MIB_UDPTABLE_OWNER_PID*>(data.data());
    if(table->dwNumEntries>(data.size()-offsetof(MIB_UDPTABLE_OWNER_PID,table))/sizeof(MIB_UDPROW_OWNER_PID))return false;
    for(DWORD i=0;i<table->dwNumEntries;i++) {
        auto& row=table->table[i];
        if(row.dwOwningPid==GetCurrentProcessId()&&ntohs(uint16_t(row.dwLocalPort))==port
            &&(row.dwLocalAddr==0||(ntohl(row.dwLocalAddr)&0xff000000)==0x7f000000))return true;
    }
    return false;
}
bool ownsUdpPort(uint32_t port){return ownsUdpFamily(port,AF_INET)||ownsUdpFamily(port,AF_INET6);}

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
    Class*(*class_get_declaring_type)(Class*);
    Class*(*class_from_type)(const Type*);
    const Method*(*class_get_methods)(Class*,void**);
    Field*(*class_get_fields)(Class*,void**);
    const Type*(*field_get_type)(Field*);
    int(*field_get_flags)(Field*);
    const char*(*field_get_name)(Field*);
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
    uint32_t(*array_length)(Object*);
    Object*(*string_new)(const char*);
    const wchar_t*(*string_chars)(Object*);
    int(*string_length)(Object*);
    void*(*thread_current)();
    GCHandle(*gchandle_new)(Object*,bool);
    Object*(*gchandle_get_target)(GCHandle);
    void(*gchandle_free)(GCHandle);
    void load() {
        HMODULE game=GetModuleHandleW(L"GameAssembly.dll");if(!game)throw std::runtime_error("GameAssembly.dll is not loaded");
#define API(member,name) member=reinterpret_cast<decltype(member)>(GetProcAddress(game,"il2cpp_" name)); if(!member)throw std::runtime_error("Missing IL2CPP export: " name)
        API(domain_get,"domain_get");API(domain_get_assemblies,"domain_get_assemblies");
        API(assembly_get_image,"assembly_get_image");API(image_get_class_count,"image_get_class_count");
        API(image_get_class,"image_get_class");API(class_get_name,"class_get_name");API(class_get_namespace,"class_get_namespace");
        API(class_get_declaring_type,"class_get_declaring_type");API(class_from_type,"class_from_type");
        API(class_get_methods,"class_get_methods");API(class_get_fields,"class_get_fields");
        API(field_get_type,"field_get_type");API(field_get_flags,"field_get_flags");API(field_get_name,"field_get_name");API(field_static_get_value,"field_static_get_value");
        API(method_get_name,"method_get_name");API(method_get_param_count,"method_get_param_count");
        API(method_get_param,"method_get_param");API(method_get_return_type,"method_get_return_type");API(method_get_flags,"method_get_flags");
        API(type_get_name,"type_get_name");API(free_,"free");API(runtime_invoke,"runtime_invoke");API(string_new,"string_new");
        API(class_get_type,"class_get_type");API(type_get_object,"type_get_object");API(object_unbox,"object_unbox");API(array_length,"array_length");
        API(string_chars,"string_chars");API(string_length,"string_length");API(thread_current,"thread_current");
        API(gchandle_new,"gchandle_new");API(gchandle_get_target,"gchandle_get_target");API(gchandle_free,"gchandle_free");
#undef API
    }
    std::string name(const Type* type){char* p=type_get_name(type);if(!p)return {};std::string s=p;free_(p);return s;}
    std::string name(Class* type){
        if(auto parent=class_get_declaring_type(type))return name(parent)+"+"+class_get_name(type);
        std::string ns=class_get_namespace(type);return ns.empty()?class_get_name(type):ns+"."+class_get_name(type);
    }
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
const Method *setActive,*setName,*objectAlive;
Object *gameObjectType=nullptr,*networkableType=nullptr;
Object* manager=nullptr;
bool signature(const Method* method,const char* result,const std::vector<const char*>& params) {
    if(api.method_get_param_count(method)!=params.size()||api.name(api.method_get_return_type(method))!=result)return false;
    uint32_t i=0;for(auto p:params)if(api.name(api.method_get_param(method,i++))!=p)return false;
    return true;
}

struct Binding {const char* role;const char* owner;const char* member;const char* result;bool isStatic;std::vector<const char*> params;const Method** slot;};
const std::vector<Binding>& bindings() {
    static const std::vector<Binding> result={
        {"transform", "UnityEngine.GameObject", "get_transform", "UnityEngine.Transform", false, {}, &getTransform},
        {"scene", "UnityEngine.GameObject", "get_scene", "UnityEngine.SceneManagement.Scene", false, {}, &getScene},
        {"component", "UnityEngine.GameObject", "GetComponent", "UnityEngine.Component", false, {"System.Type"}, &getComponent},
        {"name", "UnityEngine.Object", "get_name", "System.String", false, {}, &getName},
        {"position", "UnityEngine.Transform", "get_position", "UnityEngine.Vector3", false, {}, &getPosition},
        {"valid scene", "UnityEngine.SceneManagement.Scene", "IsValid", "System.Boolean", false, {}, &sceneValid},
        {"object search", "UnityEngine.Resources", "FindObjectsOfTypeAll", "UnityEngine.Object[]", true, {"System.Type"}, &findObjects},
        {"array element", "System.Array", "GetValue", "System.Object", false, {"System.Int32"}, &arrayGet},
        {"move", "UnityEngine.Transform", "set_position", "System.Void", false, {"UnityEngine.Vector3"}, &setPosition},
        {"rotate", "UnityEngine.Transform", "set_rotation", "System.Void", false, {"UnityEngine.Quaternion"}, &setRotation},
        {"scale", "UnityEngine.Transform", "set_localScale", "System.Void", false, {"UnityEngine.Vector3"}, &setScale},
        {"destroy", "UnityEngine.Object", "Destroy", "System.Void", true, {"UnityEngine.Object"}, &destroyObject},
        {"instantiate", "UnityEngine.Object", "Instantiate", "UnityEngine.Object", true, {"UnityEngine.Object", "UnityEngine.Vector3", "UnityEngine.Quaternion"}, &createPrefab},
        {"activate", "UnityEngine.GameObject", "SetActive", "System.Void", false, {"System.Boolean"}, &setActive},
        {"name placement", "UnityEngine.Object", "set_name", "System.Void", false, {"System.String"}, &setName},
        {"object lifetime", "UnityEngine.Object", "op_Implicit", "System.Boolean", true, {"UnityEngine.Object"}, &objectAlive},
    };
    return result;
}
void resolveApi() {
    for(auto& binding:bindings())*binding.slot=nullptr;
    gameObjectType=nullptr;networkableType=nullptr;manager=nullptr;findPrefab=nullptr;
    size_t count=0;auto assemblies=api.domain_get_assemblies(api.domain_get(),&count);
    if(!assemblies||count>4096)throw std::runtime_error("IL2CPP assemblies are unavailable");
    int loaders=0,singletons=0;
    for(size_t a=0;a<count;a++) {
        auto image=api.assembly_get_image(assemblies[a]);size_t total=api.image_get_class_count(image);
        for(size_t c=0;c<total;c++) {
            Class* klass=api.image_get_class(image,c);if(!klass)continue;
            std::string type=api.name(klass);void* it=nullptr;
            if(type=="UnityEngine.GameObject")gameObjectType=api.type_get_object(api.class_get_type(klass));
            if(type=="BaseNetworkable")networkableType=api.type_get_object(api.class_get_type(klass));
            if(type!="Bootstrap+<>c"&&std::none_of(bindings().begin(),bindings().end(),[&](const Binding& b){return type==b.owner;}))continue;
            if(type=="Bootstrap+<>c")while(Field* f=api.class_get_fields(klass,&it)) {
                if((api.field_get_flags(f)&0x10)&&std::string(api.field_get_name(f))=="<>9"
                    &&api.class_from_type(api.field_get_type(f))==klass) {
                    Object* value=nullptr;api.field_static_get_value(f,&value);
                    if(value){manager=value;singletons++;}
                }
            }
            it=nullptr;
            while(const Method* m=api.class_get_methods(klass,&it)) {
                std::string name=api.method_get_name(m);
                uint32_t implementation=0;bool isStatic=(api.method_get_flags(m,&implementation)&0x10)!=0;
                for(auto& b:bindings())if(type==b.owner&&name==b.member&&isStatic==b.isStatic&&signature(m,b.result,b.params)) {
                    if(*b.slot)throw std::runtime_error(std::string("Ambiguous Unity preview API: ")+b.role);
                    *b.slot=m;
                }
                // This genuine callback remains typed and invokable even when
                // the GameManager methods behind it are obfuscated.
                if(type=="Bootstrap+<>c"&&name.rfind("<Init_Tier0>b__",0)==0&&!isStatic
                    &&signature(m,"UnityEngine.GameObject",{"System.String"})) {
                    findPrefab=m;loaders++;
                }
            }
        }
    }
    std::string missing;
    for(auto& b:bindings())if(!*b.slot)missing+=(missing.empty()?"":", ")+std::string(b.role);
    if(loaders!=1||singletons!=1||!manager||!findPrefab||!gameObjectType||!networkableType||!missing.empty())
        throw std::runtime_error("Preview API unavailable: typed bootstrap loaders="+std::to_string(loaders)
            +", loader instances="+std::to_string(singletons)+(missing.empty()?"":"; missing Unity methods: "+missing));
}
void initialize() {
    api.load();if(!api.thread_current())throw std::runtime_error("The game window is not on an IL2CPP main thread");
    resolveApi();
    ready=true;
}

bool inPreviewWorld(std::string& reason) {
    reason="Join the local preview server using Copy IP.";
    if(!exists(L"client.connected"))return false;
    reason="Waiting for a fresh local server heartbeat.";
    if(!serverFresh())return false;
    auto peer=decodePeer(readBytes(L"client.connected",2108));
    FILETIME time;GetSystemTimeAsFileTime(&time);ULARGE_INTEGER value{};value.LowPart=time.dwLowDateTime;value.HighPart=time.dwHighDateTime;
    int64_t now=int64_t(value.QuadPart/10000)-11644473600000LL;
    reason="The local connection report is stale or belongs to another preview session.";
    if(!matchingPeer(peer,readText(L"session.token"),decimal(readText(L"server.pid")),readText(L"map.url"),now))return false;
    reason="Cannot verify that this Rust process owns the local server's peer UDP port.";
    return ownsUdpPort(peer.port);
}

struct Placement {uint64_t key;uint32_t uid;std::string path;Vec pos;Quat rot;Vec scale;};
struct Instance {GCHandle handle;uint32_t uid;Vec pos;Quat rot;Vec scale;};
std::map<uint64_t,Instance> objects;
bool baseline=false;
std::vector<Placement> decode(const std::vector<uint8_t>& data,uint64_t& revision) {
    if(data.size()<20||data.size()>16*1024*1024||memcmp(data.data(),"RUSLIVE1",8))throw std::runtime_error("Invalid preview snapshot");
    size_t offset=8;revision=take<uint64_t>(data,offset);uint32_t count=take<uint32_t>(data,offset);
    if(!revision||revision>INT64_MAX||count>2000)throw std::runtime_error("Invalid preview revision or count");std::vector<Placement> rows;std::map<uint64_t,bool> keys;
    for(uint32_t i=0;i<count;i++) {
        Placement p;p.key=take<uint64_t>(data,offset);p.uid=take<uint32_t>(data,offset);auto length=take<uint32_t>(data,offset);
        if(!p.key||!p.uid||keys.count(p.key)||length>4096||offset+length>data.size())throw std::runtime_error("Invalid preview placement");
        keys[p.key]=true;p.path=std::string(reinterpret_cast<const char*>(data.data()+offset),length);offset+=length;
        if(p.path.rfind("assets/",0)!=0||p.path.find("..")!=std::string::npos||p.path.find('\0')!=std::string::npos
                ||p.path.find('\\')!=std::string::npos||p.path.size()<7||p.path.substr(p.path.size()-7)!=".prefab"
                ||!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,p.path.data(),int(p.path.size()),nullptr,0))throw std::runtime_error("Invalid prefab path");
        p.pos=take<Vec>(data,offset);p.rot=take<Quat>(data,offset);p.scale=take<Vec>(data,offset);
        float values[10];memcpy(values,&p.pos,12);memcpy(values+3,&p.rot,16);memcpy(values+7,&p.scale,12);
        for(float v:values)if(!std::isfinite(v)||fabs(v)>=1e7)throw std::runtime_error("Invalid preview transform");
        double norm=double(p.rot.x)*p.rot.x+double(p.rot.y)*p.rot.y+double(p.rot.z)*p.rot.z+double(p.rot.w)*p.rot.w;
        if(fabs(norm-1)>.001||fabs(p.scale.x)<1e-6||fabs(p.scale.y)<1e-6||fabs(p.scale.z)<1e-6)throw std::runtime_error("Invalid scale or rotation");
        rows.push_back(p);
    }
    if(offset!=data.size())throw std::runtime_error("Unexpected snapshot data");return rows;
}
void remove(Instance instance) {
    try {Object* value=api.gchandle_get_target(instance.handle);if(value){void* args[]={value};api.call(destroyObject,nullptr,args);}}
    catch(...){api.gchandle_free(instance.handle);throw;}
    api.gchandle_free(instance.handle);
}
void discard(std::map<uint64_t,Instance>& values) noexcept {for(auto& entry:values)try{remove(entry.second);}catch(...){}values.clear();}
void clear() {discard(objects);applied=0;attempted=0;appliedCount=0;}
bool retainedAlive() {
    for(auto& entry:objects){
        Object* value=api.gchandle_get_target(entry.second.handle);if(!value)return false;
        void* args[]={value};Object* result=api.call(objectAlive,nullptr,args);
        if(!result||!*static_cast<bool*>(api.object_unbox(result)))return false;
    }
    return true;
}
void forgetWorld() {
    for(auto& entry:objects)api.gchandle_free(entry.second.handle);
    objects.clear();applied=0;attempted=0;appliedCount=0;baseline=false;
}
bool isNetworked(Object* object) {void* args[]={networkableType};return api.call(getComponent,object,args)!=nullptr;}
void claimInitial() {
    auto data=readBytes(L"initial.bin",16*1024*1024);uint64_t revision;auto rows=decode(data,revision);
    if(rows.empty()){baseline=true;return;}
    void* args[]={gameObjectType};Object* all=api.call(findObjects,nullptr,args);
    if(!all)throw std::runtime_error("Game object lookup is unavailable");
    auto count=api.array_length(all);
    if(count>1000000)throw std::runtime_error("Game object lookup exceeds preview limits");
    std::map<std::string,std::vector<Object*>> byPath;
    for(auto& p:rows)byPath[p.path];
    for(uintptr_t i=0;i<count;i++) {
        int index=int(i);void* indexArgs[]={&index};Object* obj=api.call(arrayGet,all,indexArgs);
        if(!obj)continue;
        auto name=api.text(api.call(getName,obj));auto found=byPath.find(name);if(found==byPath.end())continue;
        Object* scene=api.call(getScene,obj);Object* valid=api.call(sceneValid,api.object_unbox(scene));
        if(valid&&*static_cast<bool*>(api.object_unbox(valid)))found->second.push_back(obj);
    }
    std::map<uint64_t,Instance> claimed;
    try {
        for(auto& p:rows) {
            Object* path=api.string_new(p.path.c_str());void* lookup[]={path};
            Object* prefab=api.call(findPrefab,manager,lookup);
            if(prefab&&isNetworked(prefab))continue;
            Object* match=nullptr;auto& candidates=byPath[p.path];
            for(auto it=candidates.begin();it!=candidates.end();++it){
                Object* transform=api.call(getTransform,*it);Object* boxed=api.call(getPosition,transform);
                Vec pos=*static_cast<Vec*>(api.object_unbox(boxed));
                if(fabs(pos.x-p.pos.x)<.005&&fabs(pos.y-p.pos.y)<.005&&fabs(pos.z-p.pos.z)<.005){match=*it;candidates.erase(it);break;}
            }
            if(!match)throw std::runtime_error("Waiting for the initial map object: "+p.path);
            if(!isNetworked(match)) {
                auto handle=api.gchandle_new(match,false);
                if(!handle)throw std::runtime_error("Could not retain an initial preview object");
                claimed[p.key]={handle,p.uid,p.pos,p.rot,p.scale};
            }
        }
    }catch(...){for(auto& entry:claimed)api.gchandle_free(entry.second.handle);throw;}
    objects.swap(claimed);baseline=true;
}

void apply(const std::vector<Placement>& rows) {
    std::map<uint64_t,Instance> staged;
    std::map<uint64_t,bool> present;
    try {
        for(auto& p:rows) {
            Object* path=api.string_new(p.path.c_str());void* lookup[]={path};
            Object* prefab=api.call(findPrefab,manager,lookup);
            if(!prefab)throw std::runtime_error("Rust could not load "+p.path+". Restart preview with this asset in the initial scene.");
            if(isNetworked(prefab))continue;
            present[p.key]=true;auto found=objects.find(p.key);
            if(found!=objects.end()) {
                auto& old=found->second;
                if(old.uid==p.uid&&!memcmp(&old.pos,&p.pos,sizeof(Vec))&&!memcmp(&old.rot,&p.rot,sizeof(Quat))
                        &&!memcmp(&old.scale,&p.scale,sizeof(Vec)))continue;
            }
            // Stage replacements through the original lifecycle before retiring
            // anything. A failed create preserves the complete previous scene.
            void* args[]={prefab,const_cast<Vec*>(&p.pos),const_cast<Quat*>(&p.rot)};
            Object* obj=api.call(createPrefab,nullptr,args);
            if(!obj)throw std::runtime_error("Rust could not create "+p.path);
            auto handle=api.gchandle_new(obj,false);
            if(!handle){void* destroy[]={obj};api.call(destroyObject,nullptr,destroy);throw std::runtime_error("Could not retain a preview object");}
            staged[p.key]={handle,p.uid,p.pos,p.rot,p.scale};
            Object* transform=api.call(getTransform,obj);
            void* pos[]={const_cast<Vec*>(&p.pos)};void* rot[]={const_cast<Quat*>(&p.rot)};void* scale[]={const_cast<Vec*>(&p.scale)};
            api.call(setPosition,transform,pos);api.call(setRotation,transform,rot);api.call(setScale,transform,scale);
            void* nameArgs[]={path};api.call(setName,obj,nameArgs);
            bool active=true;void* activation[]={&active};api.call(setActive,obj,activation);
        }
    }catch(...){discard(staged);throw;}
    for(auto it=objects.begin();it!=objects.end();) {
        if(!present.count(it->first)||staged.count(it->first)){
            // A Unity destroy failure must not leak a retained handle or skip
            // cleanup of the rest of this bounded transaction.
            try{remove(it->second);}catch(...){}
            it=objects.erase(it);
        }else ++it;
    }
    objects.merge(staged);
}

LRESULT CALLBACK onMessage(int code,WPARAM wp,LPARAM lp) {
    if(code>=0&&wp==PM_REMOVE&&reinterpret_cast<MSG*>(lp)->message==PREVIEW_MESSAGE) {
        if(callbackActive.test_and_set())return CallNextHookEx(hook,code,wp,lp);
        try {
            if(GetCurrentThreadId()!=windowThread)throw std::runtime_error("Wrong Unity window thread");
            if(stopping){if(ready)clear();stopped=true;}
            else if(initializationFailed){}
            else {
            if(!ready)try{initialize();}catch(...){initializationFailed=true;throw;}
            std::string connectionReason;
            if(!inPreviewWorld(connectionReason)){
                // A delayed heartbeat or unavailable UDP table pauses edits.
                // Keep ownership through transient failures; otherwise moved
                // baseline objects could no longer be claimed after recovery.
                status("WAITING",connectionReason);
            }
            else {
                if(baseline&&!retainedAlive())forgetWorld();
                if(!baseline)claimInitial();
                std::vector<uint8_t> data;{std::lock_guard<std::mutex> lock(pendingMutex);data=pending;}
                if(!data.empty()) {
                    size_t offset=8;uint64_t revision=take<uint64_t>(data,offset);
                    uint64_t serverRevision=0;
                    try {serverRevision=std::stoull(readText(L"server.revision"));} catch(...) {}
                    if(revision>applied && revision!=attempted && serverRevision==revision) {
                        attempted=revision;
                        auto rows=decode(data,revision);
                        apply(rows);
                        applied=revision;appliedCount=rows.size();
                    }
                }
                // Restore Ready after a pause even when no edit was made.
                // Preserve a failed revision's error until a newer edit arrives.
                if(applied&&attempted==applied)status("READY","Live scene revision "+std::to_string(applied)+" applied ("+std::to_string(appliedCount)+" placements).");
            }
            }
        }catch(const std::exception& error){status("ERROR",error.what());}
        catch(...){status("ERROR","Unexpected preview error. Restart your computer before launching Rust again after injection.");}
        callbackActive.clear();
    }
    return CallNextHookEx(hook,code,wp,lp);
}
BOOL CALLBACK findWindow(HWND hwnd,LPARAM) {
    DWORD pid;DWORD thread=GetWindowThreadProcessId(hwnd,&pid);wchar_t name[256];
    if(pid==GetCurrentProcessId()&&GetClassNameW(hwnd,name,256)&&std::wstring(name)==L"UnityWndClass"){
        window=hwnd;windowThread=thread;return FALSE;
    }return TRUE;
}
DWORD WINAPI run(void*) {try {
    if(!eacOff()){status("BLOCKED","EAC state failed verification inside the preview module.");return 1;}
    EnumWindows(findWindow,0);
    if(!window){status("ERROR","Rust has no Unity game window yet.");return 2;}
    hook=SetWindowsHookExW(WH_GETMESSAGE,onMessage,module,windowThread);
    if(!hook){status("ERROR","Could not register the local main-thread preview callback.");return 3;}
    status("STARTING","Waiting for the Unity main thread and local preview map.");
    while(exists(L"active.flag")&&!exists(L"stop.flag")&&!exists(L"server.blocked")) {
        if(initializationFailed){UnhookWindowsHookEx(hook);return 8;}
        if(!eacOff()){status("BLOCKED","EAC became active or unreadable. Preview has stopped.");UnhookWindowsHookEx(hook);return 4;}
        // A missing/locked/replaced heartbeat pauses this iteration, never the
        // worker. EAC and session-stop checks still run on every iteration, and
        // the main-thread callback independently revalidates connection proof.
        if(queueSnapshot())PostMessageW(window,PREVIEW_MESSAGE,0,0);
        Sleep(250);
    }
    if(exists(L"server.blocked"))status("BLOCKED","The local server blocked this preview session. See server.blocked in Preview Logs.");
    else status("STOPPED","The Ruster preview session ended or Stop was requested. Close Rust fully before starting a new injected session.");
    stopping=true;PostMessageW(window,PREVIEW_MESSAGE,0,0);
    for(int i=0;i<40&&!stopped;i++)Sleep(50);
    UnhookWindowsHookEx(hook);return 0;
}catch(const std::exception& error){status("ERROR",error.what());if(hook)UnhookWindowsHookEx(hook);return 6;}
catch(...){status("ERROR","Unexpected preview worker error");if(hook)UnhookWindowsHookEx(hook);return 7;}
}
}

extern "C" __declspec(dllexport) DWORD WINAPI RusterStart(void* argument) {
    // A DLL stays mapped until Rust exits. Reusing it could mix session state or
    // an updated on-disk export with an older loaded build.
    if(worker)return 5;
    try {
    if(!argument||!eacOff())return 1;
    stopping=false;stopped=false;baseline=false;applied=0;appliedCount=0;
    directory=static_cast<const wchar_t*>(argument);
    if(directory.size()>30000||!exists(L"active.flag")||exists(L"stop.flag")||!exists(L"scene.bin")||!exists(L"map.url")||!exists(L"session.token"))return 2;
    worker=CreateThread(nullptr,0,run,nullptr,0,nullptr);return worker?0:3;
    }catch(...){return 6;}
}
BOOL WINAPI DllMain(HINSTANCE self,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH){module=self;DisableThreadLibraryCalls(self);}return TRUE;
}

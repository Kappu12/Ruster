// Standalone native parser check. Does not call eacOff, RusterStart or game APIs.
#include "../ruster/preview_native/client.cpp"
#include <iostream>
#include <memory>
#include <ws2tcpip.h>

// Synthetic IL2CPP callbacks exercise transaction rollback without game APIs.
namespace {
// Model the published Unity 6 ABI independently of the bridge declarations.
// A pointer above 4 GiB exposes truncated return values, stored fields and calls.
using RuntimeHandle=void*;
std::map<RuntimeHandle,Object*> retained;
std::vector<uintptr_t> destroyed;
uintptr_t nextHandle=0x0000025600000002ULL;
uintptr_t nextObject=1000;
bool rejectScale=false;
uintptr_t rejectDeactivate=0;
std::map<uintptr_t,bool> activeObjects;
int physicsSyncs=0;
RuntimeHandle retainFake(Object* obj,bool){auto handle=reinterpret_cast<RuntimeHandle>(nextHandle++);retained[handle]=obj;return handle;}
Object* targetFake(RuntimeHandle handle){return retained.at(handle);}
void freeFake(RuntimeHandle handle){retained.erase(handle);}
Object* invokeFake(const Method* method,void* self,void** args,Object**) {
    if(method==findPrefab){
        if(self!=manager)throw std::runtime_error("Prefab lookup did not use the bootstrap instance");
        return strstr(reinterpret_cast<const char*>(args[0]),"missing")?nullptr:reinterpret_cast<Object*>(500);
    }
    if(method==getComponent)return nullptr;
    if(method==createPrefab){
        if(self||args[0]!=reinterpret_cast<Object*>(500)||static_cast<Vec*>(args[1])->z!=-3.f)
            throw std::runtime_error("Unity Instantiate received an invalid object/transform ABI");
        return reinterpret_cast<Object*>(nextObject++);
    }
    if(method==setScale&&rejectScale)throw std::runtime_error("Synthetic setter rejection");
    if(method==setActive){
        auto id=reinterpret_cast<uintptr_t>(self);bool enabled=*static_cast<bool*>(args[0]);
        if(!enabled&&id==rejectDeactivate)throw std::runtime_error("Synthetic collider retirement rejection");
        activeObjects[id]=enabled;
    }
    if(method==syncPhysics)physicsSyncs++;
    if(method==getTransform)return static_cast<Object*>(self);
    if(method==objectAlive){static bool alive=true;return reinterpret_cast<Object*>(&alive);}
    if(method==destroyObject){
        auto id=reinterpret_cast<uintptr_t>(args[0]);
        if(activeObjects[id])throw std::runtime_error("Deferred destroy left an active stale collider");
        destroyed.push_back(id);
    }
    return nullptr;
}
void transactionCheck() {
    findPrefab=reinterpret_cast<Method*>(1);getComponent=reinterpret_cast<Method*>(2);
    createPrefab=reinterpret_cast<Method*>(3);getTransform=reinterpret_cast<Method*>(4);
    destroyObject=reinterpret_cast<Method*>(5);setPosition=reinterpret_cast<Method*>(6);
    setRotation=reinterpret_cast<Method*>(7);setScale=reinterpret_cast<Method*>(8);
    setActive=reinterpret_cast<Method*>(9);setName=reinterpret_cast<Method*>(10);objectAlive=reinterpret_cast<Method*>(11);
    syncPhysics=reinterpret_cast<Method*>(12);manager=reinterpret_cast<Object*>(99);
    api.runtime_invoke=invokeFake;
    api.string_new=[](const char* p){return reinterpret_cast<Object*>(const_cast<char*>(p));};
    api.gchandle_new=reinterpret_cast<decltype(api.gchandle_new)>(retainFake);
    api.gchandle_get_target=reinterpret_cast<decltype(api.gchandle_get_target)>(targetFake);
    api.gchandle_free=reinterpret_cast<decltype(api.gchandle_free)>(freeFake);
    api.object_unbox=[](Object* p){return static_cast<void*>(p);};
    Object* value=reinterpret_cast<Object*>(501);auto handle=api.gchandle_new(value,false);
    if((uintptr_t)handle<=UINT32_MAX)throw std::runtime_error("Unity 6 GCHandle return value was truncated to 32 bits");
    if(api.gchandle_get_target(handle)!=value)throw std::runtime_error("Unity 6 GCHandle lookup lost upper pointer bits");
    api.gchandle_free(handle);
    if(!retained.empty())throw std::runtime_error("Unity 6 GCHandle free lost upper pointer bits");
    auto original=reinterpret_cast<RuntimeHandle>(0x0000025600000001ULL);
    retained[original]=reinterpret_cast<Object*>(101);
    activeObjects[101]=true;
    objects[17]={(decltype(Instance{}.handle))(uintptr_t)original,1,{0,0,0},{0,0,0,1},{1,1,1}};
    Placement p{17,123456,"assets/test/source.prefab",{1,2,-3},{0,0,0,1},{1,2,3}};
    Placement missing=p;missing.key=18;missing.path="assets/test/missing.prefab";
    bool failed=false;
    try{apply({p,missing});}catch(const std::exception&){failed=true;}
    if(!failed||objects.size()!=1||(uintptr_t)objects.at(17).handle!=(uintptr_t)original||retained.size()!=1||destroyed!=std::vector<uintptr_t>{1000})
        throw std::runtime_error("A failed replacement damaged the previous scene");
    apply({p});
    if(!retainedAlive())throw std::runtime_error("Post-spawn retained-object polling failed");
    if(objects.size()!=1||objects.at(17).uid!=123456||retained.size()!=1||destroyed.back()!=101)
        throw std::runtime_error("Successful replacement did not retire the old object");
    auto added=p;added.key=18;added.path="assets/test/new-on-the-fly.prefab";
    apply({p,added});
    if(objects.size()!=2||objects.at(17).uid!=123456||retained.size()!=2)
        throw std::runtime_error("A newly introduced asset could not be added");
    for(auto& entry:objects)if((uintptr_t)entry.second.handle<=UINT32_MAX)throw std::runtime_error("Stored GCHandle was truncated");
    if(!retainedAlive())throw std::runtime_error("Polling newly added objects lost their handles");
    auto old=objects.at(18).handle;added.scale.x=2;rejectScale=true;failed=false;
    try{apply({p,added});}catch(const std::exception&){failed=true;}
    rejectScale=false;
    if(!failed||objects.at(18).handle!=old||retained.size()!=2)
        throw std::runtime_error("A failed activation/transform damaged the old scene");
    // Native movement/no-build identities use the same transaction. Exercise
    // move/rotate/resize, then replay prior snapshots as editor undo and redo do.
    auto movement=p;movement.uid=3521578167u;movement.path="assets/test/prevent_movment_volume.prefab";
    auto noBuild=added;noBuild.uid=4190049974u;noBuild.path="assets/test/prevent_building_cube.prefab";
    apply({movement,noBuild});
    auto baseline=noBuild;
    for(int edit=0;edit<3;edit++) {
        auto oldObject=reinterpret_cast<uintptr_t>(targetFake(objects.at(18).handle));
        int beforeSync=physicsSyncs;
        if(edit==0)noBuild.pos.x+=10;
        if(edit==1)noBuild.rot={0,.70710677f,0,.70710677f};
        if(edit==2)noBuild.scale={133.25f,64.25f,133.25f};
        apply({movement,noBuild});
        if(activeObjects[oldObject]||physicsSyncs<=beforeSync||objects.at(18).uid!=4190049974u)
            throw std::runtime_error("A volume edit retained old collision or lost its native identity");
    }
    apply({movement,baseline});apply({movement,noBuild});
    auto oldMovement=objects.at(17).handle,oldNoBuild=objects.at(18).handle;
    rejectDeactivate=reinterpret_cast<uintptr_t>(targetFake(oldNoBuild));failed=false;
    try{apply({});}catch(const std::exception&){failed=true;}
    rejectDeactivate=0;
    if(!failed||objects.at(17).handle!=oldMovement||objects.at(18).handle!=oldNoBuild||retained.size()!=2||
        !activeObjects[reinterpret_cast<uintptr_t>(targetFake(oldMovement))])
        throw std::runtime_error("A failed collider retirement did not restore the previous scene");
    apply({movement});apply({movement,noBuild});apply({movement});
    apply({});
    if(!objects.empty()||!retained.empty())throw std::runtime_error("Deletion leaked preview handles");
    apply({p});forgetWorld();
    if(!objects.empty()||!retained.empty())throw std::runtime_error("World cleanup lost upper handle bits");
}
struct FakeClass;
struct FakeType {std::string name;FakeClass* klass=nullptr;};
struct FakeMethod {std::string name;FakeType result;std::vector<FakeType> params;bool isStatic;};
struct FakeClass {std::string name,space;FakeClass* parent=nullptr;FakeType type;std::vector<std::unique_ptr<FakeMethod>> methods;};
std::vector<std::unique_ptr<FakeClass>> classes;
FakeClass* bootstrap=nullptr;
FakeClass* fakeClass(std::string name,std::string space="",FakeClass* parent=nullptr) {
    auto value=std::make_unique<FakeClass>();value->name=name;value->space=space;value->parent=parent;
    auto ptr=value.get();value->type={space.empty()?name:space+"."+name,ptr};classes.push_back(std::move(value));return ptr;
}
void reflectionCheck() {
    classes.clear();std::map<std::string,FakeClass*> owners;
    for(auto& b:bindings()) {
        auto& klass=owners[b.owner];
        if(!klass){std::string owner=b.owner;auto split=owner.find_last_of('.');klass=fakeClass(owner.substr(split+1),owner.substr(0,split));}
        auto m=std::make_unique<FakeMethod>();m->name=b.member;m->result={b.result};m->isStatic=b.isStatic;
        for(auto p:b.params)m->params.push_back({p});klass->methods.push_back(std::move(m));
    }
    fakeClass("BaseNetworkable");auto parent=fakeClass("Bootstrap");bootstrap=fakeClass("<>c","",parent);
    auto loader=std::make_unique<FakeMethod>();loader->name="<Init_Tier0>b__42_0";loader->result={"UnityEngine.GameObject"};loader->params.push_back({"System.String"});loader->isStatic=false;
    bootstrap->methods.push_back(std::move(loader));
    api.domain_get=[]()->void*{return reinterpret_cast<void*>(1);};
    api.domain_get_assemblies=[](void*,size_t* count)->const Assembly**{static const Assembly* rows[]={reinterpret_cast<Assembly*>(1)};*count=1;return rows;};
    api.assembly_get_image=[](const Assembly*){return reinterpret_cast<const Image*>(1);};
    api.image_get_class_count=[](const Image*){return classes.size();};
    api.image_get_class=[](const Image*,size_t i){return reinterpret_cast<Class*>(classes.at(i).get());};
    api.class_get_name=[](Class* p){return reinterpret_cast<FakeClass*>(p)->name.c_str();};
    api.class_get_namespace=[](Class* p){return reinterpret_cast<FakeClass*>(p)->space.c_str();};
    api.class_get_declaring_type=[](Class* p){return reinterpret_cast<Class*>(reinterpret_cast<FakeClass*>(p)->parent);};
    api.class_get_type=[](Class* p){return reinterpret_cast<const Type*>(&reinterpret_cast<FakeClass*>(p)->type);};
    api.class_from_type=[](const Type* p){return reinterpret_cast<Class*>(reinterpret_cast<const FakeType*>(p)->klass);};
    api.type_get_object=[](const Type* p){return reinterpret_cast<Object*>(const_cast<Type*>(p));};
    api.type_get_name=[](const Type* p){auto s=reinterpret_cast<const FakeType*>(p)->name;auto copy=new char[s.size()+1];memcpy(copy,s.c_str(),s.size()+1);return copy;};
    api.free_=[](void* p){delete[] static_cast<char*>(p);};
    api.class_get_methods=[](Class* p,void** iterator)->const Method*{
        auto& methods=reinterpret_cast<FakeClass*>(p)->methods;auto i=reinterpret_cast<uintptr_t>(*iterator);
        if(i>=methods.size())return nullptr;*iterator=reinterpret_cast<void*>(i+1);return reinterpret_cast<Method*>(methods[i].get());
    };
    api.method_get_name=[](const Method* p){return reinterpret_cast<const FakeMethod*>(p)->name.c_str();};
    api.method_get_return_type=[](const Method* p){return reinterpret_cast<const Type*>(&reinterpret_cast<const FakeMethod*>(p)->result);};
    api.method_get_param_count=[](const Method* p){return uint32_t(reinterpret_cast<const FakeMethod*>(p)->params.size());};
    api.method_get_param=[](const Method* p,uint32_t i){return reinterpret_cast<const Type*>(&reinterpret_cast<const FakeMethod*>(p)->params.at(i));};
    api.method_get_flags=[](const Method* p,uint32_t* impl){*impl=0;return uint32_t(reinterpret_cast<const FakeMethod*>(p)->isStatic?0x10:0);};
    api.class_get_fields=[](Class* p,void** iterator)->Field*{
        if(p!=reinterpret_cast<Class*>(bootstrap)||*iterator)return nullptr;*iterator=reinterpret_cast<void*>(1);return reinterpret_cast<Field*>(1);
    };
    api.field_get_name=[](Field*){return "<>9";};api.field_get_flags=[](Field*){return 0x10;};
    api.field_get_type=[](Field*){return reinterpret_cast<const Type*>(&bootstrap->type);};
    api.field_static_get_value=[](Field*,void* p){*static_cast<Object**>(p)=reinterpret_cast<Object*>(99);};
    // No GameManager factory or WorldSerialization metadata in this fixture.
    resolveApi();
    auto factory=createPrefab;
    auto duplicate=std::make_unique<FakeMethod>(*bootstrap->methods[0]);bootstrap->methods.push_back(std::move(duplicate));
    bool failed=false;try{resolveApi();}catch(const std::exception&){failed=true;}
    if(!failed)throw std::runtime_error("Ambiguous bootstrap loader was accepted");bootstrap->methods.pop_back();
    auto& object=owners.at("UnityEngine.Object");
    for(auto& m:object->methods)if(m.get()==reinterpret_cast<const FakeMethod*>(factory)){object->methods.push_back(std::make_unique<FakeMethod>(*m));break;}
    failed=false;try{resolveApi();}catch(const std::exception&){failed=true;}
    if(!failed)throw std::runtime_error("Ambiguous Unity factory was accepted");object->methods.pop_back();
    auto& methods=owners.at("UnityEngine.Transform")->methods;methods.erase(methods.begin());
    failed=false;try{resolveApi();}catch(const std::exception&){failed=true;}
    if(!failed)throw std::runtime_error("Incomplete Unity bindings were accepted");
}
void peerCheck() {
    Peer peer{std::string(64,'a'),"http://127.0.0.1:12345/test.map",123,23456,10000};
    if(!matchingPeer(peer,peer.token,123,peer.url,11000)||matchingPeer(peer,peer.token,123,peer.url,12000)
        ||matchingPeer(peer,std::string(64,'b'),123,peer.url,11000)||matchingPeer(peer,peer.token,456,peer.url,11000)
        ||matchingPeer(peer,peer.token,123,"http://127.0.0.1:12345/other.map",11000))throw std::runtime_error("Foreign/stale connection proof accepted");
    WSADATA data;if(WSAStartup(MAKEWORD(2,2),&data))throw std::runtime_error("Synthetic socket setup failed");
    SOCKET socket=::socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(socket==INVALID_SOCKET||bind(socket,reinterpret_cast<sockaddr*>(&address),sizeof(address)))throw std::runtime_error("Synthetic socket bind failed");
    int size=sizeof(address);getsockname(socket,reinterpret_cast<sockaddr*>(&address),&size);auto port=ntohs(address.sin_port);
    if(!ownsUdpPort(port)||ownsUdpPort(0))throw std::runtime_error("UDP ownership check failed");closesocket(socket);
    if(ownsUdpPort(port))throw std::runtime_error("Closed UDP endpoint was accepted");
    socket=::socket(AF_INET6,SOCK_DGRAM,IPPROTO_UDP);
    if(socket!=INVALID_SOCKET) {
        sockaddr_in6 address6{};address6.sin6_family=AF_INET6;reinterpret_cast<uint8_t*>(&address6.sin6_addr)[15]=1;
        if(bind(socket,reinterpret_cast<sockaddr*>(&address6),sizeof(address6)))throw std::runtime_error("Synthetic IPv6 socket bind failed");
        size=sizeof(address6);getsockname(socket,reinterpret_cast<sockaddr*>(&address6),&size);port=ntohs(address6.sin6_port);
        if(!ownsUdpPort(port))throw std::runtime_error("IPv6 UDP ownership check failed");closesocket(socket);
    }
    WSACleanup();
}
void heartbeatCheck(const std::filesystem::path& input) {
    // Only disposable fixture files next to this standalone decoder's input.
    // Never call RusterStart, the worker, EAC probing or any Unity API here.
    auto root=input.parent_path()/L"heartbeat-fixture";
    if(!std::filesystem::create_directory(root))throw std::runtime_error("Heartbeat fixture already exists");
    struct Fixture {
        std::filesystem::path path;std::wstring previous;
        ~Fixture(){directory=previous;std::error_code ignored;std::filesystem::remove_all(path,ignored);}
    } fixture{root,directory};
    directory=root.wstring();lastStatus.clear();
    std::vector<uint8_t> snapshot(20);memcpy(snapshot.data(),"RUSLIVE1",8);snapshot[8]=3;
    {std::ofstream out(root/L"scene.bin",std::ios::binary);out.write(reinterpret_cast<const char*>(snapshot.data()),snapshot.size());}
    pending={42};
    if(queueSnapshot()||!pending.empty()||stopping||stopped)throw std::runtime_error("Missing heartbeat did not pause safely");
    auto fresh=[&](){std::ofstream out(root/L"server.ready");out<<"synthetic heartbeat";};
    fresh();
    if(!queueSnapshot()||pending!=snapshot)throw std::runtime_error("Preview did not resume after its first heartbeat");
    std::filesystem::rename(root/L"server.ready",root/L"held.ready");
    if(queueSnapshot()||!pending.empty())throw std::runtime_error("Heartbeat replacement gap allowed a cached edit");
    std::filesystem::rename(root/L"held.ready",root/L"server.ready");
    if(!queueSnapshot()||pending!=snapshot)throw std::runtime_error("Heartbeat replacement permanently stopped polling");
    HANDLE heartbeat=CreateFileW((root/L"server.ready").c_str(),FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);
    if(heartbeat==INVALID_HANDLE_VALUE)throw std::runtime_error("Fixture timestamp setup failed");
    FILETIME time;GetSystemTimeAsFileTime(&time);ULARGE_INTEGER value{};value.LowPart=time.dwLowDateTime;value.HighPart=time.dwHighDateTime;
    value.QuadPart-=200000000;time.dwLowDateTime=value.LowPart;time.dwHighDateTime=value.HighPart;
    bool updated=SetFileTime(heartbeat,nullptr,nullptr,&time)!=FALSE;CloseHandle(heartbeat);
    if(!updated||queueSnapshot()||!pending.empty())throw std::runtime_error("An expired heartbeat allowed edits");
    fresh();
    if(!queueSnapshot())throw std::runtime_error("An expired heartbeat permanently stopped polling");
    HANDLE locked=CreateFileW((root/L"scene.bin").c_str(),GENERIC_READ,0,nullptr,OPEN_EXISTING,0,nullptr);
    if(locked==INVALID_HANDLE_VALUE)throw std::runtime_error("Fixture snapshot lock failed");
    bool queued=queueSnapshot();CloseHandle(locked);
    if(queued||!pending.empty())throw std::runtime_error("A locked snapshot did not pause safely");
    if(!queueSnapshot()||pending!=snapshot)throw std::runtime_error("A temporary snapshot lock permanently stopped polling");
    // The history survives later status updates, while identical polls do not
    // grow it at 4 Hz. A malformed snapshot still fails rather than applying.
    status("READY","Synthetic recovered revision");auto bytes=std::filesystem::file_size(root/L"client.log");
    status("READY","Synthetic recovered revision");
    if(std::filesystem::file_size(root/L"client.log")!=bytes)throw std::runtime_error("Duplicate status flooded the transition log");
    auto history=readText(L"client.log");
    if(history.find("WAITING")==std::string::npos||history.find("READY Synthetic recovered revision")==std::string::npos)
        throw std::runtime_error("Status changes erased the preview interruption history");
    {std::ofstream out(root/L"client.log",std::ios::binary);out<<std::string(1024*1024+1,'x');}
    status("WAITING","Synthetic bounded history");
    if(std::filesystem::file_size(root/L"client.log")>4096||readText(L"client.log").find("Synthetic bounded history")==std::string::npos)
        throw std::runtime_error("Status history exceeded its size bound");
    {std::ofstream out(root/L"scene.bin",std::ios::binary);out<<"bad";}
    bool failed=false;try{queueSnapshot();}catch(const std::runtime_error&){failed=true;}
    if(!failed)throw std::runtime_error("Malformed snapshot accepted after recovery");
    pending.clear();lastStatus.clear();
}
}
int main(int argc,char** argv) {
    bool peerMode=argc==3&&std::string(argv[1])=="--peer";
    if(argc!=2&&!peerMode)return 2;
    if(!eacName(L"C:\\Game\\EasyAntiCheat_EOS.sys")||!eacName(L"EAC_Client.dll")||eacName(L"GameAssembly.dll"))return 3;
    try {
        reflectionCheck();transactionCheck();peerCheck();heartbeatCheck(std::filesystem::path(argv[peerMode?2:1]));
        std::ifstream input(argv[peerMode?2:1],std::ios::binary);
        std::vector<uint8_t> data{std::istreambuf_iterator<char>(input),{}};
        if(peerMode) {
            auto peer=decodePeer(data);
            if(!matchingPeer(peer,std::string(64,'a'),123,"http://127.0.0.1:12345/test.map",11000))return 1;
            return 0;
        }
        uint64_t revision;auto rows=decode(data,revision);
        std::cout<<revision<<" "<<rows.size()<<"\n";
        if(!rows.empty()&&(rows[0].key!=17||rows[0].uid!=123456||rows[0].pos.z!=-3.f||rows[0].scale.y!=2.f))return 4;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}
}

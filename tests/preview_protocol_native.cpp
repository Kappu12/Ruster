// Standalone native parser check. Does not call eacOff, RusterStart or game APIs.
#include "../ruster/preview_native/client.cpp"
#include <iostream>
#include <memory>
#include <ws2tcpip.h>

// Synthetic IL2CPP callbacks exercise transaction rollback without game APIs.
namespace {
std::map<uint32_t,Object*> retained;
std::vector<uintptr_t> destroyed;
uint32_t nextHandle=2;
uintptr_t nextObject=1000;
bool rejectScale=false;
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
    if(method==getTransform)return static_cast<Object*>(self);
    if(method==destroyObject)destroyed.push_back(reinterpret_cast<uintptr_t>(args[0]));
    return nullptr;
}
void transactionCheck() {
    findPrefab=reinterpret_cast<Method*>(1);getComponent=reinterpret_cast<Method*>(2);
    createPrefab=reinterpret_cast<Method*>(3);getTransform=reinterpret_cast<Method*>(4);
    destroyObject=reinterpret_cast<Method*>(5);setPosition=reinterpret_cast<Method*>(6);
    setRotation=reinterpret_cast<Method*>(7);setScale=reinterpret_cast<Method*>(8);
    setActive=reinterpret_cast<Method*>(9);setName=reinterpret_cast<Method*>(10);manager=reinterpret_cast<Object*>(99);
    api.runtime_invoke=invokeFake;
    api.string_new=[](const char* p){return reinterpret_cast<Object*>(const_cast<char*>(p));};
    api.gchandle_new=[](Object* obj,bool){auto handle=nextHandle++;retained[handle]=obj;return handle;};
    api.gchandle_get_target=[](uint32_t handle){return retained.at(handle);};
    api.gchandle_free=[](uint32_t handle){retained.erase(handle);};
    retained[1]=reinterpret_cast<Object*>(101);
    objects[17]={1,1,{0,0,0},{0,0,0,1},{1,1,1}};
    Placement p{17,123456,"assets/test/source.prefab",{1,2,-3},{0,0,0,1},{1,2,3}};
    Placement missing=p;missing.key=18;missing.path="assets/test/missing.prefab";
    bool failed=false;
    try{apply({p,missing});}catch(const std::exception&){failed=true;}
    if(!failed||objects.size()!=1||objects.at(17).handle!=1||retained.size()!=1||destroyed!=std::vector<uintptr_t>{1000})
        throw std::runtime_error("A failed replacement damaged the previous scene");
    apply({p});
    if(objects.size()!=1||objects.at(17).uid!=123456||retained.size()!=1||destroyed.back()!=101)
        throw std::runtime_error("Successful replacement did not retire the old object");
    auto added=p;added.key=18;added.path="assets/test/new-on-the-fly.prefab";
    apply({p,added});
    if(objects.size()!=2||objects.at(17).uid!=123456||retained.size()!=2)
        throw std::runtime_error("A newly introduced asset could not be added");
    auto old=objects.at(18).handle;added.scale.x=2;rejectScale=true;failed=false;
    try{apply({p,added});}catch(const std::exception&){failed=true;}
    rejectScale=false;
    if(!failed||objects.at(18).handle!=old||retained.size()!=2)
        throw std::runtime_error("A failed activation/transform damaged the old scene");
    apply({});
    if(!objects.empty()||!retained.empty())throw std::runtime_error("Deletion leaked preview handles");
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
}
int main(int argc,char** argv) {
    bool peerMode=argc==3&&std::string(argv[1])=="--peer";
    if(argc!=2&&!peerMode)return 2;
    if(!eacName(L"C:\\Game\\EasyAntiCheat_EOS.sys")||!eacName(L"EAC_Client.dll")||eacName(L"GameAssembly.dll"))return 3;
    try {
        reflectionCheck();transactionCheck();peerCheck();
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

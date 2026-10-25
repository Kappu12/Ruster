// Standalone native parser check. Does not call eacOff, RusterStart or game APIs.
#include "../ruster/preview_native/client.cpp"
#include <iostream>

// Synthetic IL2CPP callbacks exercise transaction rollback without game APIs.
namespace {
std::map<uint32_t,Object*> retained;
std::vector<uintptr_t> destroyed;
uint32_t nextHandle=2;
uintptr_t nextObject=1000;
Object* invokeFake(const Method* method,void* self,void** args,Object**) {
    if(method==findPrefab)return strstr(reinterpret_cast<const char*>(args[0]),"missing")?nullptr:reinterpret_cast<Object*>(500);
    if(method==getComponent)return nullptr;
    if(method==createPrefab)return reinterpret_cast<Object*>(nextObject++);
    if(method==getTransform)return static_cast<Object*>(self);
    if(method==destroyObject)destroyed.push_back(reinterpret_cast<uintptr_t>(args[0]));
    return nullptr;
}
void transactionCheck() {
    findPrefab=reinterpret_cast<Method*>(1);getComponent=reinterpret_cast<Method*>(2);
    createPrefab=reinterpret_cast<Method*>(3);getTransform=reinterpret_cast<Method*>(4);
    destroyObject=reinterpret_cast<Method*>(5);setPosition=reinterpret_cast<Method*>(6);
    setRotation=reinterpret_cast<Method*>(7);setScale=reinterpret_cast<Method*>(8);
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
    apply({});
    if(!objects.empty()||!retained.empty())throw std::runtime_error("Deletion leaked preview handles");
}
}
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    if(!eacName(L"C:\\Game\\EasyAntiCheat_EOS.sys")||!eacName(L"EAC_Client.dll")||eacName(L"GameAssembly.dll"))return 3;
    try {
        transactionCheck();
        std::ifstream input(argv[1],std::ios::binary);
        std::vector<uint8_t> data{std::istreambuf_iterator<char>(input),{}};
        uint64_t revision;auto rows=decode(data,revision);
        std::cout<<revision<<" "<<rows.size()<<"\n";
        if(!rows.empty()&&(rows[0].key!=17||rows[0].uid!=123456||rows[0].pos.z!=-3.f||rows[0].scale.y!=2.f))return 4;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}
}

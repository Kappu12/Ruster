// Standalone native parser check. Does not call eacOff, RusterStart or game APIs.
#include "../ruster/preview_native/client.cpp"
#include <iostream>
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    if(!eacName(L"C:\\Game\\EasyAntiCheat_EOS.sys")||!eacName(L"EAC_Client.dll")||eacName(L"GameAssembly.dll"))return 3;
    try {
        std::ifstream input(argv[1],std::ios::binary);
        std::vector<uint8_t> data{std::istreambuf_iterator<char>(input),{}};
        uint64_t revision;auto rows=decode(data,revision);
        std::cout<<revision<<" "<<rows.size()<<"\n";
        if(!rows.empty()&&(rows[0].key!=17||rows[0].uid!=123456||rows[0].pos.z!=-3.f||rows[0].scale.y!=2.f))return 4;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}
}

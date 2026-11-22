// fm3unzip: extract FM3's zip archives (Xbox LZX method 21, deflate, store) using the FM3 recomp's own readers
// (FM3-ReGPU src/zip.cpp, src/lzx.cpp, compiled in from that checkout).
//   fm3unzip <archive.zip> <out dir> [filter substring]
#include "zip.h"
#include <cstdio>
#include <filesystem>
#include <fstream>

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::printf("fm3unzip <archive.zip> <out dir> [filter]\n");
        return 2;
    }
    const std::filesystem::path out = argv[2];
    int n = 0;
    ForEachZipMemberInFile(argv[1], argc > 3 ? argv[3] : "", [&](const std::string& name, const std::vector<uint8_t>& data) {
        std::filesystem::path p = out / std::filesystem::path(name);
        std::filesystem::create_directories(p.parent_path());
        std::ofstream(p, std::ios::binary).write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
        n++;
    });
    std::printf("%d members extracted\n", n);
    return n ? 0 : 1;
}

#include <cstring>
#include <iostream>
#include <string_view>

extern "C" {
#include "health.h"
}

int main(int argc, char **argv) {
  if (argc == 2 && std::string_view(argv[1]) == "--version") {
    std::cout << "nrtk-engine 0.1.0\n";
    return 0;
  }
  std::cout << "nrtk-engine health: " << nrtk_engine_status() << '\n';
  std::cout << "Phase 1 foundation only; no GNSS processing is implemented.\n";
  return argc > 1 && std::strcmp(argv[1], "--health") != 0 ? 2 : 0;
}

# Out-of-tree build of the RadiationModel probe of chapter 10 (no Python binding exists for RadiationModel).
# -DPYHARP_SRC=<pyharp tree at the pin> -DPYHARP_BUILD=<that tree>/build -DDISORT_INC=<site-packages>/pydisort
cmake_minimum_required(VERSION 3.18)
project(ch10_model_probe CXX)
set(CMAKE_CXX_STANDARD 17)
list(APPEND CMAKE_MODULE_PATH ${PYHARP_SRC}/cmake/modules)
find_program(Python3_EXECUTABLE NAMES python)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(Torch REQUIRED)
execute_process(COMMAND python -c "import torch; print(int(torch._C._GLIBCXX_USE_CXX11_ABI))" OUTPUT_VARIABLE ABI OUTPUT_STRIP_TRAILING_WHITESPACE)
add_compile_definitions(_GLIBCXX_USE_CXX11_ABI=${ABI})
add_executable(model_probe ${CMAKE_CURRENT_SOURCE_DIR}/model_probe.cpp)
target_include_directories(model_probe PRIVATE ${PYHARP_BUILD} ${PYHARP_SRC} ${DISORT_INC}
  ${PYHARP_BUILD}/_deps/fmt-src/include ${PYHARP_BUILD}/_deps/yaml-cpp-src/include
  ${TORCH_INCLUDE_DIR} ${TORCH_API_INCLUDE_DIR})
target_link_options(model_probe PRIVATE -Wl,--no-as-needed)
target_link_libraries(model_probe PRIVATE ${PYHARP_BUILD}/lib/libharp_release.so
  ${DISORT_INC}/lib/libdisort_release.so ${PYHARP_BUILD}/lib/libyaml-cpp.a ${PYHARP_BUILD}/lib/libfmt.a
  torch netcdf pthread)

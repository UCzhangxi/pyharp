# Out-of-tree build of pyharp C++ test files that tests/CMakeLists.txt does not
# register. -DPYHARP_SRC=<worktree> -DPYHARP_BUILD=<worktree>/build -DDISORT_INC=<site>/pydisort
cmake_minimum_required(VERSION 3.18)
project(pyharp_extra_tests CXX)
set(CMAKE_CXX_STANDARD 17)
list(APPEND CMAKE_MODULE_PATH ${PYHARP_SRC}/cmake/modules)
find_program(Python3_EXECUTABLE NAMES python)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(Torch REQUIRED)
enable_testing()
execute_process(COMMAND python -c "import torch; print(int(torch._C._GLIBCXX_USE_CXX11_ABI))" OUTPUT_VARIABLE ABI OUTPUT_STRIP_TRAILING_WHITESPACE)
add_compile_definitions(_GLIBCXX_USE_CXX11_ABI=${ABI})
foreach(t ${EXTRA_TESTS})
  add_executable(${t} ${PYHARP_SRC}/tests/${t}.cpp)
  target_include_directories(${t} PRIVATE ${PYHARP_BUILD} ${PYHARP_SRC} ${DISORT_INC}
    ${PYHARP_BUILD}/_deps/fmt-src/include ${PYHARP_BUILD}/_deps/yaml-cpp-src/include
    ${PYHARP_BUILD}/_deps/gtest-src/googletest/include ${TORCH_INCLUDE_DIR} ${TORCH_API_INCLUDE_DIR})
  target_link_options(${t} PRIVATE -Wl,--no-as-needed)
  target_link_libraries(${t} PRIVATE ${PYHARP_BUILD}/lib/libharp_release.so
    ${DISORT_INC}/lib/libdisort_release.so ${PYHARP_BUILD}/lib/libgtest_main.a
    ${PYHARP_BUILD}/lib/libgtest.a ${PYHARP_BUILD}/lib/libyaml-cpp.a ${PYHARP_BUILD}/lib/libfmt.a
    torch netcdf pthread)
  add_test(NAME ${t} COMMAND ${t} WORKING_DIRECTORY ${CMAKE_BINARY_DIR}/run)
endforeach()

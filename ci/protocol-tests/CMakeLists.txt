# Fast, platform-independent protocol checks without the Qt desktop build.
cmake_minimum_required(VERSION 3.21)
project(aspia_clipboard_protocol_tests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
find_package(Protobuf REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(ICU REQUIRED COMPONENTS uc)
find_package(GTest REQUIRED)
get_filename_component(ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/proto")
set(PROTO_SOURCES)
foreach(NAME common desktop file_transfer clipboard_file)
    add_custom_command(OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.cc" "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.h"
        COMMAND protobuf::protoc "--cpp_out=${CMAKE_CURRENT_BINARY_DIR}/proto" "-I${ROOT}/source/proto" "${ROOT}/source/proto/${NAME}.proto"
        DEPENDS "${ROOT}/source/proto/${NAME}.proto")
    list(APPEND PROTO_SOURCES "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.cc")
endforeach()
add_executable(clipboard_protocol_tests
    ${PROTO_SOURCES}
    ${ROOT}/source/common/clipboard_file_transfer.cc
    ${ROOT}/source/common/clipboard_file_transfer_unittest.cc
    ${ROOT}/source/common/file_packetizer.cc
    ${ROOT}/source/client/input_event_filter.cc
    ${ROOT}/source/client/input_event_filter_unittest.cc
    ${ROOT}/source/base/crypto/random.cc
    ${ROOT}/source/base/logging.cc
    ${ROOT}/source/base/debug.cc
    ${ROOT}/source/base/environment.cc
    ${ROOT}/source/base/system_time.cc
    ${ROOT}/source/base/system_error.cc
    ${ROOT}/source/base/scoped_clear_last_error.cc
    ${ROOT}/source/base/memory/byte_array.cc
    ${ROOT}/source/base/strings/string_number_conversions.cc
    ${ROOT}/source/base/strings/string_util.cc
    ${ROOT}/source/base/strings/string_util_constants.cc
    ${ROOT}/source/base/strings/unicode.cc)
target_include_directories(clipboard_protocol_tests PRIVATE "${ROOT}/source" "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(clipboard_protocol_tests PRIVATE protobuf::libprotobuf-lite OpenSSL::Crypto ICU::uc GTest::gtest_main)
enable_testing()
add_test(NAME clipboard_protocol_tests COMMAND clipboard_protocol_tests)

# Audit storage and report logic without the full desktop/video dependency tree.
cmake_minimum_required(VERSION 3.21)
project(aspia_audit_inventory_tests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Protobuf REQUIRED)
find_package(SQLite3 REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Core Widgets)
find_package(OpenSSL REQUIRED)
find_package(GTest REQUIRED)
find_path(ASIO_INCLUDE_DIR asio/ip/tcp.hpp REQUIRED)
# Match the real desktop build so this gate also catches QStringBuilder and
# implicit Qt conversion errors instead of accepting a looser translation unit.
add_compile_definitions(QT_NO_CAST_TO_ASCII QT_NO_CAST_FROM_BYTEARRAY
    QT_USE_QSTRINGBUILDER ASIO_STANDALONE ASIO_NO_DEPRECATED)
get_filename_component(ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/proto")
set(PROTO_SOURCES)
set(PROTO_NAMES common desktop address_book system_info session_audit inventory
    key_exchange router_common router_admin desktop_extensions desktop_internal
    relay_peer router_peer router_relay task_manager text_chat)
set(PROTO_INPUTS)
foreach(NAME IN LISTS PROTO_NAMES)
    list(APPEND PROTO_INPUTS "${ROOT}/source/proto/${NAME}.proto")
endforeach()
foreach(NAME IN LISTS PROTO_NAMES)
    add_custom_command(
        OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.cc" "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.h"
        COMMAND protobuf::protoc "--cpp_out=${CMAKE_CURRENT_BINARY_DIR}/proto" "-I${ROOT}/source/proto" "${ROOT}/source/proto/${NAME}.proto"
        DEPENDS ${PROTO_INPUTS}
        VERBATIM)
    list(APPEND PROTO_SOURCES "${CMAKE_CURRENT_BINARY_DIR}/proto/${NAME}.pb.cc")
endforeach()
add_executable(audit_inventory_tests
    ${PROTO_SOURCES}
    ${ROOT}/source/common/session_audit_store.cc
    ${ROOT}/source/common/session_audit_store_unittest.cc
    ${ROOT}/source/common/inventory_store.cc
    ${ROOT}/source/common/inventory_store_unittest.cc
    ${ROOT}/source/client/ui/router_manager/session_audit_helpers.cc
    ${ROOT}/source/client/session_audit_helpers_unittest.cc
    ${ROOT}/source/console/inventory_report.cc
    ${ROOT}/source/console/inventory_report_unittest.cc
    ${ROOT}/source/client/client_config.cc
    ${ROOT}/source/client/router_config.cc
    ${ROOT}/source/base/crypto/secure_memory.cc)
target_include_directories(audit_inventory_tests PRIVATE "${ROOT}/source" "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(audit_inventory_tests PRIVATE protobuf::libprotobuf-lite SQLite::SQLite3 Qt5::Core OpenSSL::Crypto GTest::gtest_main)
enable_testing()
add_test(NAME audit_inventory_tests COMMAND audit_inventory_tests)

# Compile both new UI surfaces, their moc output and the transport plumbing on
# Linux before spending time on Windows dependencies. Native input/OLE and the
# Host collector still need the full Windows build and interactive acceptance.
add_library(audit_widget_syntax OBJECT
    ${ROOT}/source/client/ui/router_manager/session_audit_widget.cc
    ${ROOT}/source/client/ui/router_manager/session_audit_widget.h
    ${ROOT}/source/console/inventory_dialog.cc
    ${ROOT}/source/console/inventory_dialog.h
    ${ROOT}/source/client/router.cc
    ${ROOT}/source/client/router_proxy.cc
    ${ROOT}/source/client/router_window_proxy.cc
    ${ROOT}/source/base/peer/relay_peer.cc
    ${ROOT}/source/host/client_session.cc
    ${ROOT}/source/router/session_client.cc)
set_target_properties(audit_widget_syntax PROPERTIES AUTOMOC ON)
target_include_directories(audit_widget_syntax PRIVATE "${ROOT}/source" "${CMAKE_CURRENT_BINARY_DIR}" "${ASIO_INCLUDE_DIR}")
target_link_libraries(audit_widget_syntax PRIVATE Qt5::Widgets protobuf::libprotobuf-lite OpenSSL::Crypto)
add_dependencies(audit_widget_syntax audit_inventory_tests)

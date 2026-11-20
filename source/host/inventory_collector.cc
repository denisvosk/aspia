// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#include "host/inventory_collector.h"

#include "base/task_runner.h"
#include "base/crypto/random.h"
#include "base/sys_info.h"
#include "base/strings/unicode.h"
#include "base/files/base_paths.h"
#include "build/build_config.h"

#include <atomic>
#include <chrono>
#include <limits>
#include <set>
#include <vector>

#if defined(OS_WIN)
#include "base/smbios_parser.h"
#include "base/smbios_reader.h"
#include "base/win/drive_enumerator.h"
#include "base/win/scoped_object.h"

#include <Windows.h>
#include <SetupAPI.h>
#include <winioctl.h>
#endif

namespace host {

namespace {

int64_t nowSeconds()
{
    return std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

#if defined(OS_WIN)

// GUID_DEVINTERFACE_DISK from ntddstor.h, defined locally to avoid a UUID-library dependency.
const GUID kDiskInterface = {0x53f56307, 0xb6bf, 0x11d0,
    {0x94, 0xf2, 0x00, 0xa0, 0xc9, 0x1e, 0xfb, 0x8b}};

std::string descriptorString(const std::vector<uint8_t>& buffer, DWORD offset)
{
    if (!offset || offset >= buffer.size())
        return {};
    const char* start = reinterpret_cast<const char*>(buffer.data() + offset);
    size_t length = 0;
    while (offset + length < buffer.size() && start[length])
        ++length;
    if (offset + length == buffer.size() || length > 1024)
        return {};
    std::string result(start, length);
    const auto first = result.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
        return {};
    result = result.substr(first, result.find_last_not_of(" \t\r\n") - first + 1);
    return result;
}

void collectDisks(proto::InventorySnapshot* snapshot)
{
    HDEVINFO devices = SetupDiGetClassDevsW(&kDiskInterface, nullptr, nullptr,
                                           DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (devices == INVALID_HANDLE_VALUE)
    {
        snapshot->set_collection_note("Physical disk enumeration is unavailable");
        return;
    }
    std::set<DWORD> seen;
    for (DWORD i = 0; i < 128; ++i)
    {
        SP_DEVICE_INTERFACE_DATA interface_data = {};
        interface_data.cbSize = sizeof(interface_data);
        if (!SetupDiEnumDeviceInterfaces(devices, nullptr, &kDiskInterface, i, &interface_data))
            break;
        DWORD required = 0;
        SetupDiGetDeviceInterfaceDetailW(devices, &interface_data, nullptr, 0, &required, nullptr);
        if (required < sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W) || required > 65536)
            continue;
        std::vector<uint8_t> details(required);
        auto detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(details.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);
        if (!SetupDiGetDeviceInterfaceDetailW(devices, &interface_data, detail, required, nullptr, nullptr))
            continue;
        base::win::ScopedHandle handle(CreateFileW(detail->DevicePath, GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr));
        if (!handle.isValid())
            continue;
        DWORD returned = 0;
        STORAGE_DEVICE_NUMBER number = {};
        if (!DeviceIoControl(handle.get(), IOCTL_STORAGE_GET_DEVICE_NUMBER, nullptr, 0,
                             &number, sizeof(number), &returned, nullptr) ||
            returned < sizeof(number) || !seen.insert(number.DeviceNumber).second)
            continue;
        auto disk = snapshot->add_disks();
        disk->set_device_number(number.DeviceNumber);
        GET_LENGTH_INFORMATION length = {};
        if (DeviceIoControl(handle.get(), IOCTL_DISK_GET_LENGTH_INFO, nullptr, 0,
                            &length, sizeof(length), &returned, nullptr) &&
            returned >= sizeof(length) && length.Length.QuadPart > 0)
            disk->set_size_bytes(static_cast<uint64_t>(length.Length.QuadPart));

        STORAGE_PROPERTY_QUERY query = {};
        query.PropertyId = StorageDeviceProperty;
        query.QueryType = PropertyStandardQuery;
        STORAGE_DESCRIPTOR_HEADER header = {};
        if (!DeviceIoControl(handle.get(), IOCTL_STORAGE_QUERY_PROPERTY, &query, sizeof(query),
                             &header, sizeof(header), &returned, nullptr) ||
            returned < sizeof(header) || header.Size < sizeof(STORAGE_DEVICE_DESCRIPTOR) || header.Size > 65536)
            continue;
        std::vector<uint8_t> buffer(header.Size);
        if (!DeviceIoControl(handle.get(), IOCTL_STORAGE_QUERY_PROPERTY, &query, sizeof(query),
                             buffer.data(), static_cast<DWORD>(buffer.size()), &returned, nullptr) ||
            returned < sizeof(STORAGE_DEVICE_DESCRIPTOR) || returned > buffer.size())
            continue;
        buffer.resize(returned);
        const auto descriptor = reinterpret_cast<const STORAGE_DEVICE_DESCRIPTOR*>(buffer.data());
        std::string model = descriptorString(buffer, descriptor->VendorIdOffset);
        const std::string product = descriptorString(buffer, descriptor->ProductIdOffset);
        if (!model.empty() && !product.empty())
            model += " ";
        model += product;
        disk->set_model(model);
        disk->set_bus_type(static_cast<uint32_t>(descriptor->BusType));

        // RAID, USB bridges and virtual SCSI devices may hide or emulate rotation. Keep them
        // UNKNOWN. TRIM support alone is deliberately not used to classify media.
        if (descriptor->BusType == BusTypeNvme)
        {
            disk->set_media(proto::InventoryDisk::SSD);
            disk->set_media_evidence("NVMe bus reported by Windows storage driver");
        }
        else if (descriptor->BusType == BusTypeAta || descriptor->BusType == BusTypeSata ||
                 descriptor->BusType == BusTypeSas)
        {
            query.PropertyId = StorageDeviceSeekPenaltyProperty;
            DEVICE_SEEK_PENALTY_DESCRIPTOR seek = {};
            if (DeviceIoControl(handle.get(), IOCTL_STORAGE_QUERY_PROPERTY, &query, sizeof(query),
                                &seek, sizeof(seek), &returned, nullptr) &&
                returned >= sizeof(seek) && seek.Size >= sizeof(seek))
            {
                disk->set_media(seek.IncursSeekPenalty ? proto::InventoryDisk::HDD : proto::InventoryDisk::SSD);
                disk->set_media_evidence("Seek penalty reported by Windows storage driver");
            }
        }
    }
    SetupDiDestroyDeviceInfoList(devices);
    if (!snapshot->disks_size())
        snapshot->set_collection_note("No physical disk information could be read");
}

void collectWindowsDetails(proto::InventorySnapshot* snapshot)
{
    DWORD mhz = 0;
    DWORD bytes = sizeof(mhz);
    if (RegGetValueW(HKEY_LOCAL_MACHINE, L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
                     L"~MHz", RRF_RT_REG_DWORD, nullptr, &mhz, &bytes) == ERROR_SUCCESS)
        snapshot->set_cpu_clock_mhz(mhz);

    ULONGLONG installed_kib = 0;
    if (GetPhysicallyInstalledSystemMemory(&installed_kib) &&
        installed_kib <= std::numeric_limits<uint64_t>::max() / 1024)
    {
        snapshot->set_ram_bytes(installed_kib * 1024);
        snapshot->set_ram_source("physically_installed");
    }
    else
    {
        MEMORYSTATUSEX status = {};
        status.dwLength = sizeof(status);
        if (GlobalMemoryStatusEx(&status))
        {
            snapshot->set_ram_bytes(status.ullTotalPhys);
            snapshot->set_ram_source("usable_physical_memory");
        }
    }

    for (base::SmbiosTableEnumerator enumerator(base::readSmbiosDump());
         !enumerator.isAtEnd(); enumerator.advance())
    {
        if (enumerator.table()->type != base::SMBIOS_TABLE_TYPE_BASEBOARD)
            continue;
        base::SmbiosBaseboard board(enumerator.table());
        if (board.isValid())
        {
            snapshot->set_board_manufacturer(board.manufacturer());
            snapshot->set_board_model(board.product());
        }
        break;
    }

    for (base::win::DriveEnumerator drives; !drives.isAtEnd(); drives.advance())
    {
        const auto& info = drives.driveInfo();
        // Do not wake removable optical media or wait on mapped network drives.
        if (info.type() != base::win::DriveEnumerator::DriveInfo::Type::FIXED)
            continue;
        auto volume = snapshot->add_volumes();
        volume->set_path(base::utf8FromWide(info.path().native()));
        volume->set_drive_type(DRIVE_FIXED);
        volume->set_file_system(info.fileSystem());
        volume->set_total_bytes(info.totalSpace());
        const uint64_t free = info.freeSpace();
        volume->set_free_bytes(free <= volume->total_bytes() ? free : 0);
    }
    collectDisks(snapshot);
}

#endif // OS_WIN

proto::InventorySnapshot collectSnapshot(base::HostId host_id)
{
    proto::InventorySnapshot snapshot;
    std::string collection_id(16, '\0');
    if (!base::Random::fillBuffer(collection_id.data(), collection_id.size()))
        return {};
    snapshot.set_collection_id(std::move(collection_id));
    snapshot.set_host_id(host_id);
    snapshot.set_computer_name(base::utf8FromUtf16(base::SysInfo::computerName()));
    snapshot.set_os_name(base::utf8FromUtf16(base::SysInfo::operatingSystemName()));
    snapshot.set_os_version(base::utf8FromUtf16(base::SysInfo::operatingSystemVersion()));
    snapshot.set_os_arch(base::utf8FromUtf16(base::SysInfo::operatingSystemArchitecture()));
    snapshot.set_cpu_model(base::utf8FromUtf16(base::SysInfo::processorName()));
    const int packages = base::SysInfo::processorPackages();
    const int cores = base::SysInfo::processorCores();
    const int threads = base::SysInfo::processorThreads();
    if (packages > 0) snapshot.set_cpu_packages(static_cast<uint32_t>(packages));
    if (cores > 0) snapshot.set_cpu_cores(static_cast<uint32_t>(cores));
    if (threads > 0) snapshot.set_cpu_threads(static_cast<uint32_t>(threads));
#if defined(OS_WIN)
    collectWindowsDetails(&snapshot);
#else
    snapshot.set_collection_note("Detailed automatic hardware inventory requires Windows Host");
#endif
    snapshot.set_collected_at(nowSeconds());
    return snapshot;
}

#if defined(OS_WIN)

proto::InventorySnapshot collectInProcess(base::HostId host_id, const std::atomic_bool& alive)
{
    std::filesystem::path folder;
    if (!base::BasePaths::currentExecDir(&folder))
        return {};
    const std::wstring executable = (folder / L"aspia_host_service.exe").native();
    std::wstring command = L"\"" + executable + L"\" --inventory-stdout";
    SECURITY_ATTRIBUTES security = {sizeof(security), nullptr, TRUE};
    HANDLE read_pipe = nullptr;
    HANDLE write_pipe = nullptr;
    if (!CreatePipe(&read_pipe, &write_pipe, &security, 0))
        return {};
    base::win::ScopedHandle input(read_pipe);
    base::win::ScopedHandle output(write_pipe);
    if (!SetHandleInformation(input.get(), HANDLE_FLAG_INHERIT, 0))
        return {};
    base::win::ScopedHandle null_handle(CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, &security, OPEN_EXISTING, 0, nullptr));
    if (!null_handle.isValid())
        return {};
    base::win::ScopedHandle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job.isValid() || !SetInformationJobObject(job.get(), JobObjectExtendedLimitInformation,
                                                  &limits, sizeof(limits)))
        return {};
    SIZE_T attribute_size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &attribute_size);
    std::vector<uint8_t> attributes(attribute_size);
    auto list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.data());
    if (!InitializeProcThreadAttributeList(list, 1, 0, &attribute_size))
        return {};
    HANDLE inherited[] = {output.get(), null_handle.get()};
    if (!UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited,
                                   sizeof(inherited), nullptr, nullptr))
    {
        DeleteProcThreadAttributeList(list);
        return {};
    }
    STARTUPINFOEXW startup = {};
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = null_handle.get();
    startup.StartupInfo.hStdError = null_handle.get();
    startup.StartupInfo.hStdOutput = output.get();
    startup.lpAttributeList = list;
    PROCESS_INFORMATION process_info = {};
    const BOOL created = CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, TRUE,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_SUSPENDED | BELOW_NORMAL_PRIORITY_CLASS,
        nullptr, folder.c_str(), &startup.StartupInfo, &process_info);
    DeleteProcThreadAttributeList(list);
    if (!created)
        return {};
    base::win::ScopedHandle process(process_info.hProcess);
    base::win::ScopedHandle thread(process_info.hThread);
    if (!AssignProcessToJobObject(job.get(), process.get()) || ResumeThread(thread.get()) == DWORD(-1))
    {
        TerminateProcess(process.get(), 1);
        return {};
    }
    output.reset();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    std::string bytes;
    bool completed = false;
    while (alive && std::chrono::steady_clock::now() < deadline)
    {
        DWORD available = 0;
        if (!PeekNamedPipe(input.get(), nullptr, 0, nullptr, &available, nullptr))
        {
            if (GetLastError() != ERROR_BROKEN_PIPE)
                break;
            completed = WaitForSingleObject(process.get(), 100) == WAIT_OBJECT_0;
            break;
        }
        if (available)
        {
            if (available > 128 * 1024 || bytes.size() + available > 128 * 1024)
                break;
            const size_t position = bytes.size();
            bytes.resize(position + available);
            DWORD read = 0;
            if (!ReadFile(input.get(), bytes.data() + position, available, &read, nullptr))
                break;
            bytes.resize(position + read);
            continue;
        }
        if (WaitForSingleObject(process.get(), 100) == WAIT_OBJECT_0)
        {
            // Drain data written just before exit on the next pass.
            if (PeekNamedPipe(input.get(), nullptr, 0, nullptr, &available, nullptr) && available)
                continue;
            completed = true;
            break;
        }
    }
    DWORD exit_code = 1;
    if (!completed || !GetExitCodeProcess(process.get(), &exit_code) || exit_code != 0)
    {
        TerminateJobObject(job.get(), 1);
        // No unbounded wait for a driver-stuck helper. Closing the job also requests termination.
        WaitForSingleObject(process.get(), 1000);
        return {};
    }
    proto::InventorySnapshot snapshot;
    if (!snapshot.ParseFromString(bytes) || snapshot.collected_at() <= 0 || snapshot.computer_name().empty())
        return {};
    snapshot.set_host_id(host_id);
    return snapshot;
}

#endif // OS_WIN

} // namespace

int runInventoryCollectorProcess()
{
#if defined(OS_WIN)
    const auto snapshot = collectSnapshot(0);
    const std::string bytes = snapshot.SerializeAsString();
    if (bytes.empty() || bytes.size() > 128 * 1024)
        return 1;
    DWORD written = 0;
    return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), bytes.data(), static_cast<DWORD>(bytes.size()),
                     &written, nullptr) && written == bytes.size() ? 0 : 1;
#else
    return 1;
#endif
}

struct InventoryCollector::State
{
    std::shared_ptr<base::TaskRunner> runner;
    std::atomic_bool alive{true};
    std::atomic_bool busy{false};
};

InventoryCollector::InventoryCollector(std::shared_ptr<base::TaskRunner> task_runner)
    : state_(std::make_shared<State>())
{
    state_->runner = std::move(task_runner);
}

InventoryCollector::~InventoryCollector()
{
    state_->alive = false;
    if (worker_.joinable())
        worker_.join();
}

bool InventoryCollector::collect(base::HostId host_id,
                                 std::function<void(proto::InventorySnapshot)> callback)
{
    if (!host_id || !callback || state_->busy.exchange(true))
        return false;
    if (worker_.joinable())
        worker_.join();
    const auto state = state_;
    try
    {
        worker_ = std::thread([state, host_id, callback = std::move(callback)]() mutable
        {
            proto::InventorySnapshot snapshot;
            try
            {
#if defined(OS_WIN)
                snapshot = collectInProcess(host_id, state->alive);
#else
                snapshot = collectSnapshot(host_id);
#endif
            }
            catch (...)
            {
                snapshot.Clear();
            }
            try
            {
                state->runner->postTask([state, snapshot = std::move(snapshot), callback = std::move(callback)]() mutable
                {
                    state->busy = false;
                    if (state->alive)
                        callback(std::move(snapshot));
                });
            }
            catch (...)
            {
                state->busy = false;
            }
        });
    }
    catch (...)
    {
        state_->busy = false;
        return false;
    }
    return true;
}

} // namespace host

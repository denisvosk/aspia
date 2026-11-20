// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later
#include "console/inventory_report.h"

#include <gtest/gtest.h>
#include <QJsonArray>
#include <QJsonDocument>

namespace console {
namespace {

TEST(InventoryReportTest, WholeBookIncludesNestedGroupsAndInheritedCredentials)
{
    proto::address_book::ComputerGroup root;
    root.set_name("Root");
    root.mutable_config()->set_username("root-user");
    root.mutable_config()->set_password("private-password");
    auto group = root.add_computer_group();
    group->set_name("Branch");
    group->mutable_config()->mutable_inherit()->set_credentials(true);
    auto pc = group->add_computer();
    pc->set_name("Workplace"); pc->set_address("12345"); pc->set_port(8050);
    pc->mutable_inherit()->set_credentials(true);
    auto nested = group->add_computer_group();
    nested->set_name("Room");
    auto second = nested->add_computer();
    second->set_name("Other"); second->set_address("direct.example"); second->set_port(8050);
    second->set_username("own-user"); second->set_password("own-password");
    const auto targets = inventoryTargets(root, std::nullopt, "Admin");
    ASSERT_EQ(targets.size(), 2);
    EXPECT_EQ(targets[0].group, QStringLiteral("Root / Branch"));
    EXPECT_EQ(targets[1].group, QStringLiteral("Root / Branch / Room"));
    EXPECT_EQ(targets[0].config.username, u"root-user");
    EXPECT_EQ(targets[1].config.username, u"own-user");
}

TEST(InventoryReportTest, EndpointIdentityScopesRouterAndIgnoresAliasesAndCredentials)
{
    client::Config first;
    first.address_or_id = u"001234";
    first.router_config = client::RouterConfig();
    first.router_config->address = u"router.example";
    first.router_config->port = 8060;
    client::Config second = first;
    second.address_or_id = u"1234";
    second.computer_name = u"New book name";
    second.username = u"Another account";
    EXPECT_EQ(inventoryEndpointKey(first), inventoryEndpointKey(second));
    second.router_config->address = u"other-router.example";
    EXPECT_NE(inventoryEndpointKey(first), inventoryEndpointKey(second));
    second = first; second.router_config->port = 8061;
    EXPECT_NE(inventoryEndpointKey(first), inventoryEndpointKey(second));
}

TEST(InventoryReportTest, SnapshotExcludesProductKeysAndUnknownFields)
{
    proto::system_info::SystemInfo info;
    info.mutable_computer()->set_name("test-pc");
    info.mutable_processor()->set_cores(2);
    info.mutable_operating_system()->set_key("DO-NOT-SAVE-KEY");
    auto module = info.mutable_memory()->add_module();
    module->set_present(true); module->set_size(8589934592ULL);
    info.mutable_memory()->add_module()->set_size(1234); // unpopulated slot
    const auto summary = inventorySummary(info, 1000);
    EXPECT_EQ(summary.value("ram_bytes").toString(), QStringLiteral("8589934592"));
    EXPECT_FALSE(QJsonDocument(summary).toJson().contains("DO-NOT-SAVE-KEY"));
}

TEST(InventoryReportTest, PhysicalDisksAreSeparateFromLogicalVolumes)
{
    proto::InventorySnapshot value;
    value.set_collected_at(1000); value.set_received_at(1001);
    value.set_ram_source("physically_installed");
    auto disk = value.add_disks();
    disk->set_model("test"); disk->set_size_bytes(1000); disk->set_media(proto::InventoryDisk::UNKNOWN);
    auto volume = value.add_volumes();
    volume->set_path("C:\\"); volume->set_total_bytes(600); volume->set_free_bytes(200);
    auto summary = inventorySummary(value);
    EXPECT_EQ(summary.value("physical_disks").toArray().size(), 1);
    EXPECT_EQ(summary.value("logical_volumes").toArray().size(), 1);
    EXPECT_EQ(summary.value("physical_disks").toArray()[0].toObject().value("size_bytes").toString(), "1000");
}

TEST(InventoryReportTest, UnknownAndFutureTimesAreNotClassifiedAsInactive)
{
    EXPECT_FALSE(inventoryTimestampIsStale(0, 4000000, 30));
    EXPECT_FALSE(inventoryTimestampIsStale(5000000, 4000000, 30));
    EXPECT_FALSE(inventoryTimestampIsStale(1408001, 4000000, 30));
    EXPECT_TRUE(inventoryTimestampIsStale(1408000, 4000000, 30));
}

TEST(InventoryReportTest, CsvEscapesFormulasQuotesAndLineBreaks)
{
    EXPECT_EQ(inventoryCsvCell("=1+1"), QStringLiteral("\"'=1+1\""));
    EXPECT_EQ(inventoryCsvCell("  @SUM(A1)"), QStringLiteral("\"'  @SUM(A1)\""));
    EXPECT_EQ(inventoryCsvCell("one;\"two\"\nthree"), QStringLiteral("\"one;\"\"two\"\"\nthree\""));
    EXPECT_TRUE(inventoryCsvRow({"a", "b"}).endsWith("\r\n"));
}

} // namespace
} // namespace console

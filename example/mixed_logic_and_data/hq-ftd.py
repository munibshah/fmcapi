"""
Configure FMC for hq-ftd, register hq-ftd and push changes to it.
"""

import fmcapi  # You can use 'from fmcapi import *' but it is best practices to keep the namespaces separate.

from fmcapi.api_objects.policy_services.accessrules import Bulk


def main():
    """
    The hq-ftd device already has 10.0.0.254 on its manage interface and the command 'configure network manager
    10.0.0.10 cisco123' has already been manually typed on the FTD's CLI.
    """
    # ### Set these variables to match your environment. ### #
    host = "192.168.1.150"
    username = "apiadmin"
    password = "Amazon@123"

    with fmcapi.FMC(
        host=host,
        username=username,
        password=password,
        autodeploy=True,
        file_logging="hq-ftd.log",
    ) as fmc1:

        # Create an ACP
        acp = fmcapi.AccessPolicies(fmc=fmc1, name="ACP Policy")
        acp.defaultAction = "BLOCK"
        # I intentionally put a "space" in the ACP name to show that fmcapi will "fix" that for you.
        acp.post()

        # Create Security Zones
        sz_inside = fmcapi.SecurityZones(
            fmc=fmc1, name="inside", interfaceMode="ROUTED"
        )
        sz_inside.post()
        sz_outside = fmcapi.SecurityZones(
            fmc=fmc1, name="outside", interfaceMode="ROUTED"
        )
        sz_outside.post()
        sz_dmz = fmcapi.SecurityZones(fmc=fmc1, name="dmz", interfaceMode="ROUTED")
        sz_dmz.post()

        # Create Network Objects
        hq_dfgw_gateway = fmcapi.Hosts(
            fmc=fmc1, name="hq-default-gateway", value="100.64.0.1"
        )
        hq_dfgw_gateway.post()
        hq_lan = fmcapi.Networks(fmc=fmc1, name="hq-lan", value="10.0.0.0/24")
        hq_lan.post()
        all_lans = fmcapi.Networks(fmc=fmc1, name="all-lans", value="10.0.0.0/8")
        all_lans.post()
        hq_fmc = fmcapi.Hosts(fmc=fmc1, name="hq_fmc", value="10.0.0.10")
        hq_fmc.post()
        fmc_public = fmcapi.Hosts(fmc=fmc1, name="fmc_public_ip", value="100.64.0.10")
        fmc_public.post()

        # Create ACP Rule to permit hq_lan traffic inside to outside.
        hq_acprule = fmcapi.AccessRules(
            fmc=fmc1,
            acp_name=acp.name,
            name="Permit HQ LAN",
            action="ALLOW",
            enabled=True,
        )
        hq_acprule.source_zone(action="add", name=sz_inside.name)
        hq_acprule.destination_zone(action="add", name=sz_outside.name)
        hq_acprule.source_network(action="add", name=hq_lan.name)
        hq_acprule.destination_network(action="add", name="any-ipv4")
        # hq_acprule.logBegin = True
        # hq_acprule.logEnd = True
        hq_acprule.post()

        # Build NAT Policy
        nat = fmcapi.FTDNatPolicies(fmc=fmc1, name="NAT Policy")
        nat.post()

        # Build NAT Rule to NAT all_lans to interface outside
        autonat = fmcapi.AutoNatRules(fmc=fmc1)
        autonat.natType = "DYNAMIC"
        autonat.interfaceInTranslatedNetwork = True
        autonat.original_network(all_lans.name)
        autonat.source_intf(name=sz_inside.name)
        autonat.destination_intf(name=sz_outside.name)
        autonat.nat_policy(name=nat.name)
        autonat.post()

        # Build NAT Rule to allow inbound traffic to FMC (Branches need to register to FMC.)
        fmc_nat = fmcapi.ManualNatRules(fmc=fmc1)
        fmc_nat.natType = "STATIC"
        fmc_nat.original_source(hq_fmc.name)
        fmc_nat.translated_source(fmc_public.name)
        fmc_nat.source_intf(name=sz_inside.name)
        fmc_nat.destination_intf(name=sz_outside.name)
        fmc_nat.nat_policy(name=nat.name)
        fmc_nat.enabled = True
        fmc_nat.post()

        # Add hq-ftd device to FMC
        hq_ftd = fmcapi.DeviceRecords(fmc=fmc1)
        # Minimum things set.
        hq_ftd.hostName = "192.168.1.152"
        hq_ftd.regKey = "cisco123"
        hq_ftd.acp(name=acp.name)
        # Other stuff I want set.
        hq_ftd.name = "hq-ftd"
        hq_ftd.licensing(action="add", name="MALWARE")
        hq_ftd.licensing(action="add", name="VPN")
        hq_ftd.licensing(action="add", name="BASE")
        hq_ftd.licensing(action="add", name="THREAT")
        hq_ftd.licensing(action="add", name="URLFilter")
        # Push to FMC to start device registration.
        hq_ftd.post(post_wait_time=300)

        # Once registration is complete configure the interfaces of hq-ftd.
        hq_ftd_g00 = fmcapi.PhysicalInterfaces(fmc=fmc1, device_name=hq_ftd.name)
        hq_ftd_g00.get(name="GigabitEthernet0/0")
        hq_ftd_g00.enabled = True
        hq_ftd_g00.ifname = "IN"
        hq_ftd_g00.static(ipv4addr="10.0.0.1", ipv4mask=24)
        hq_ftd_g00.sz(name="inside")
        hq_ftd_g00.put()

        hq_ftd_g01 = fmcapi.PhysicalInterfaces(fmc=fmc1, device_name=hq_ftd.name)
        hq_ftd_g01.get(name="GigabitEthernet0/1")
        hq_ftd_g01.enabled = True
        hq_ftd_g01.ifname = "OUT"
        hq_ftd_g01.static(ipv4addr="100.64.0.200", ipv4mask=24)
        hq_ftd_g01.sz(name="outside")
        hq_ftd_g01.put()

        # Build static default route for HQ FTD
        hq_default_route = fmcapi.IPv4StaticRoutes(fmc=fmc1, name="hq_default_route")
        hq_default_route.device(device_name=hq_ftd.name)
        hq_default_route.networks(action="add", networks=["any-ipv4"])
        hq_default_route.gw(name=hq_dfgw_gateway.name)
        hq_default_route.interfaceName = hq_ftd_g01.ifname
        hq_default_route.metricValue = 1
        hq_default_route.post()

        # Associate NAT policy with HQ FTD device.
        devices = [{"name": hq_ftd.name, "type": "device"}]
        assign_nat_policy = fmcapi.PolicyAssignments(fmc=fmc1)
        assign_nat_policy.ftd_natpolicy(name=nat.name, devices=devices)
        assign_nat_policy.post()

        # Bulk create example
        bulk = Bulk(fmc=fmc1)
        for r in range(1, 10):
            # Use acp_id instead of acp_name to avoid fmcapi looking up the acp
            # id for each rule
            rule = fmcapi.AccessRules(fmc=fmc1, acp_id=acp.id)
            rule.action = "ALLOW"
            rule.name = f"rule-{r}"
            rule.enabled = True
            bulk.add(rule)

        bulk.post()

        bulk.clear()

        # Bulk delete example
        bulk = Bulk(fmc=fmc1)
        for r in range(1, 10):
            # Use acp_id instead of acp_name to avoid fmcapi looking up the acp
            # id for each rule
            rule = fmcapi.AccessRules(fmc=fmc1, acp_id=acp.id)
            rule.name = f"rule-{r}"
            # You must perform a get on the rule so that fmcapi loads the ID
            # for the rule which is required for the deletion
            rule.get()
            bulk.add(rule)

        bulk.delete()


if __name__ == "__main__":
    main()

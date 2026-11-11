#!/usr/bin/env python3
"""Check known patch-stack invariants in a prepared Airoha kernel tree."""
import argparse
from pathlib import Path


def function(source, declaration):
    if declaration not in source:
        raise ValueError('Missing kernel function: ' + declaration)
    return source.split(declaration, 1)[1].split('\n}', 1)[0]


def check(kernel):
    mtk = (kernel / 'drivers/net/ethernet/mediatek/mtk_eth_soc.c').read_text()
    add_mac = function(mtk, 'static int mtk_add_mac(')
    airoha = (kernel / 'drivers/net/ethernet/airoha/airoha_eth.c').read_text()
    exit_flow = function((kernel / 'net/netfilter/nf_flow_table_core.c').read_text(),
                         'static void __exit nf_flow_table_module_exit(')
    realtek = (kernel / 'drivers/net/dsa/realtek/rtl8365mb_main.c').read_text()
    serial = function((kernel / 'drivers/tty/serial/8250/8250_port.c').read_text(),
                      'static void set_io_from_upio(')
    conditions = (
        (serial.count('case UPIO_AU:') == 1,
         '8250 serial I/O selection must have exactly one UPIO_AU case'),
        (add_mac.count('phylink = phylink_create(') == 1,
         'MediaTek must allocate phylink exactly once'),
        ('mac_ops = &rt5350_phylink_ops;' in add_mac and 'phy_mode, mac_ops);' in add_mac,
         'MediaTek must preserve the MT7628 MAC operations selection'),
        (realtek.count('.name = "RTL8367SB"') == 1,
         'RTL8367SB must have exactly one chip entry'),
        ('unregister_netdevice_notifier' in exit_flow and 'rcu_barrier()' in exit_flow and
         exit_flow.index('unregister_netdevice_notifier') < exit_flow.index('rcu_barrier()'),
         'Flowtable notifier removal must precede the RCU barrier'),
        ('phylink_stop(dev->phylink)' in function(airoha, 'static int airoha_dev_stop('),
         'Airoha device shutdown must stop phylink'),
        ('phylink_stop' not in function(airoha, 'static int airoha_dev_set_macaddr('),
         'Airoha MAC address changes must not contain the shutdown hunk'),
    )
    for valid, message in conditions:
        if not valid:
            raise ValueError(message)
    print('Prepared kernel patch checks passed: ' + str(kernel))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    try:
        check(args.kernel)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()

# Independent Airoha PON device profiles

In `make menuconfig`, select **Target System → Airoha ARM**, choose the matching
subtarget, then choose the exact **Target Profile** ending in `(Pon)`.
For multiple devices, enable multiple profiles and select them under
**Target Devices**. The original profiles remain available.

Each PON choice includes `kmod-airoha-xpon`, `kmod-airoha-pon-frontend`,
`airoha-ponctl`, `airoha-pond`, `airoha-pon-debug`, `luci-app-pon` and
`luci-app-iptv`. The board recipe supplies its optical frontend, Ethernet PHY,
Wi-Fi, USB and storage defaults. Router and evaluation profiles retain their
own defaults; the full PON application stack is no longer a subtarget-wide
default for every AN7581/AN7583 board.

| Subtarget | Menu label | Profile ID |
| --- | --- | --- |
| AN7581 | Gemtek XG2010G(Pon) | `gemtek_xg2010g-pon` |
| AN7581 | FiberHome HG5382A(Pon) | `fiberhome_hg5382a-pon` |
| AN7581 | FiberHome HG5585F(Pon) CT | `fiberhome_hg5585f-ct-pon` |
| AN7581 | FiberHome HG5585F(Pon) CU | `fiberhome_hg5585f-cu-pon` |
| AN7581 | FiberHome HG5585F(Pon) CT-USB-SFP | `fiberhome_hg5585f-ct-usb-sfp-pon` |
| AN7581 | FiberHome HG5585F(Pon) CU-USB-SFP | `fiberhome_hg5585f-cu-usb-sfp-pon` |
| AN7581 | ZNXT ZN515XG-D(Pon) (UBI) | `znxt_zn515xg-d-pon` |
| AN7581 | ZNXT ZN504XG-D(Pon) (UBI) | `znxt_zn504xg-d-pon` |
| AN7581 | Unionman UNG00A(Pon) | `unionman_ung00a-pon` |
| AN7581 | H3C HM2004-DU(Pon) | `h3c_hm2004-du-pon` |
| AN7581 | Nokia XG-040G-MD(Pon) (UBI) | `nokia_xg-040g-md-ubi-pon` |
| AN7581 | Nokia XG-040G-MD(Pon) (UBI-USB-SFP) | `nokia_xg-040g-md-ubi-usb-sfp-pon` |
| AN7581 | Nokia XG-040G-MD(Pon) (tcboot) | `nokia_xg-040g-md-tcboot-pon` |
| AN7581 | Nokia XG-040G-TF(Pon) (UBI) | `nokia_xg-040g-tf-ubi-pon` |
| AN7583 | Nokia XG-040G-MF(Pon) | `nokia_xg-040g-mf-pon` |
| AN7583 | Nokia XG-040G-MF(Pon) (UBI) | `nokia_xg-040g-mf-ubi-pon` |

Use the layout matching the device's installed bootloader. A `(Pon)` choice
does not convert tcboot to U-Boot/FIP or change the partition map. PON and
original profiles for a given layout use the same DTS, compatible strings and
sysupgrade archive board directory. Only the profile ID, menu model label,
output filename and additional PON package defaults differ.

The saved AN7581/AN7583 presets now select these PON choices. For the Nokia MD
tcboot layout, use `configs/an7581-tcboot.config`; see the
[tcboot build and upgrade notes](XG-040G-MD-TCBOOT.md).

The EN7523 evaluation target has no new PON profile: this source's integrated
optical drivers support AN7581 and AN7583.

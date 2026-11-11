ARCH:=aarch64
SUBTARGET:=an7581
BOARDNAME:=AN7581 / AN7566 / AN7551
CPU_TYPE:=cortex-a53
KERNELNAME:=Image dtbs
FEATURES+=pwm

DEFAULT_PACKAGES += \
	airoha-en7581-npu-firmware kmod-nf-conntrack-bridge uboot-envtools

define Target/Description
	Build firmware images for Airoha an7581 ARM based boards.
endef

# Core PON stack is maintained in package/pon. Frontends remain board-specific.
DEFAULT_PACKAGES += kmod-airoha-xpon kmod-airoha-pon-frontend airoha-ponctl airoha-pond airoha-pon-debug luci-app-pon luci-app-iptv

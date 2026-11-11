ARCH:=aarch64
SUBTARGET:=an7583
BOARDNAME:=AN7583
CPU_TYPE:=cortex-a53
KERNELNAME:=Image dtbs
FEATURES+=pwm

DEFAULT_PACKAGES += \
	airoha-an7583-npu-firmware kmod-leds-gpio \
	kmod-gpio-button-hotplug uboot-envtools

define Target/Description
	Build firmware images for Airoha an7583 ARM based boards.
endef


# Core PON stack is maintained in package/pon. Frontends remain board-specific.
DEFAULT_PACKAGES += kmod-airoha-xpon kmod-airoha-pon-frontend airoha-ponctl airoha-pond airoha-pon-debug luci-app-pon luci-app-iptv

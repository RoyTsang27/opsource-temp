# Complete optical networking stack for explicitly selected PON profiles.
# The underlying board recipe supplies its optical frontend, PHY and Wi-Fi.
AIROHA_PON_PACKAGES := \
  kmod-airoha-xpon kmod-airoha-pon-frontend \
  airoha-ponctl airoha-pond airoha-pon-debug luci-app-pon luci-app-iptv

# $(1): original board/layout profile; $(2): model shown in menuconfig.
# Preserve the original compatible strings, DTS and image/bootloader layout.
# The new profile ID only adds an explicit PON choice and distinct filenames.
define Device/AirohaPonProfile
define Device/$(1)-pon
  SUPPORTED_DEVICES := $(subst _,$(comma),$(1))
  BOARD_NAME := $(1)
  $$(call Device/$(1))
  DEVICE_MODEL := $(2)(Pon)
  DEVICE_PACKAGES += $$(AIROHA_PON_PACKAGES)
endef
TARGET_DEVICES += $(1)-pon
endef

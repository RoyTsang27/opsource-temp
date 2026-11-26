# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

BOARD:=zte
BOARDNAME:=ZTE SoCs
SUBTARGETS:=zx279133
FEATURES:=dt gpio usb jffs2
KERNEL_PATCHVER:=6.18
# Match the prepared external ZX279133 kernel independently of the generic series.
override LINUX_VERSION-6.18 := .60

ifeq ($(DUMP)$(call qstrip,$(CONFIG_EXTERNAL_KERNEL_TREE)),)
  $(error Run python3 scripts/device-build.py configure sk-d840n to prepare the ZX279133 kernel)
endif

include $(INCLUDE_DIR)/target.mk

$(eval $(call BuildTarget))

# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk
JFFS2_BLOCKSIZE := 128k
include $(INCLUDE_DIR)/image.mk

KERNEL_LOADADDR := 0x80200000

define Build/skd840n-gzip
	zopfli --i10 --gzip -c "$@" > "$@.gz"
	gzip -t "$@.gz"
	mv "$@.gz" "$@"
endef

include zx279133.mk

$(eval $(call BuildImage))

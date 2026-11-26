# SPDX-License-Identifier: GPL-2.0-only

define Device/skyworth_sk-d840n
  DEVICE_VENDOR := Skyworth
  DEVICE_MODEL := SK-D840N
  DEVICE_DTS := zx279133-sk-d840n
  DEVICE_DTS_DIR := $(DTS_DIR)/zte
  DEVICE_PACKAGES := sk-layout-check
  SUPPORTED_DEVICES := skyworth,sk-d840n
  KERNEL_NAME := Image
  KERNEL_SUFFIX := .uImage
  KERNEL_SIZE := 8192k
  KERNEL_DEPENDS := $$(KDIR)/image-zx279133-sk-d840n.dtb
  KERNEL := kernel-bin | skd840n-gzip | uImage gzip
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 246784k
  FILESYSTEMS := jffs2-128k
  IMAGES := rootfs.jffs2 sysupgrade.bin
  IMAGE/rootfs.jffs2 := append-rootfs | check-size
  IMAGE/sysupgrade.bin := sysupgrade-tar dtb=$$(KDIR)/image-zx279133-sk-d840n.dtb | append-metadata
endef
TARGET_DEVICES += skyworth_sk-d840n

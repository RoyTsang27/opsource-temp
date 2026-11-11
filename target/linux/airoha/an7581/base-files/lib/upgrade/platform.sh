RAMFS_COPY_BIN='fitblk fit_check_sign'

REQUIRE_IMAGE_METADATA=1

nokia_initial_setup()
{
	[ "$(rootfs_type)" = "tmpfs" ] || return 0

	fw_setenv bootcmd "flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000"
}

nokia_tcboot_check_image()
{
	local dir="sysupgrade-${1//,/_}"
	local image="$2"
	local entries

	# The NAND helper also accepts raw FIT and UBI images. Restrict this
	# layout to the board's own upgrade archive, even with sysupgrade -F.
	entries="$(tar tf "$image" 2>/dev/null)" &&
		[ "$entries" = "$dir/
$dir/CONTROL
$dir/kernel
$dir/root" ] &&
		[ "$(identify_tar "$image" cat "$dir/kernel")" = "fit" ] &&
		[ "$(identify_tar "$image" cat "$dir/root")" = "squashfs" ] && return 0

	echo "Use the tcboot sysupgrade image for $1."
	return 1
}

nokia_tcboot_check_layout()
{
	local ubidev

	# Refuse layouts that would make nand_do_upgrade format the partition.
	ubidev="$(nand_find_ubi ubi)"
	[ -n "$ubidev" ] &&
		[ -n "$(nand_find_volume "$ubidev" kernel)" ] &&
		[ -n "$(nand_find_volume "$ubidev" rootfs)" ] && return 0

	echo "The tcboot kernel and rootfs volumes are missing."
	return 1
}

platform_check_image() {
	local board=$(board_name)

	[ "$#" -gt 1 ] && return 1

	case "$board" in
	nokia,xg-040g-md)
		nand_do_platform_check "$board" "$1"
		return $?
		;;
	nokia,xg-040g-md-tcboot|\
	nokia,xg-140g-tf-tcboot)
		nokia_tcboot_check_image "$board" "$1"
		return $?
		;;
	nokia,xg-040g-md-ubi|\
	quantum,q1000k-ubi)
		fit_check_image "$1"
		return $?
		;;
	esac

	return 0
}

platform_do_upgrade() {
	local board=$(board_name)

	case "$board" in
		nokia,xg-040g-md-tcboot|\
		nokia,xg-140g-tf-tcboot)
			nokia_tcboot_check_image "$board" "$1" &&
				nokia_tcboot_check_layout || return 1
			CI_SKIP_KERNEL_MTD=1
			nand_do_upgrade "$1"
			;;
		gemtek,w1700k-ubi|\
		nokia,xg-040g-md-ubi|\
		quantum,q1000k-ubi)
			fit_do_upgrade "$1"
			;;
		*)
			nand_do_upgrade "$1"
			;;
	esac
}

platform_pre_upgrade() {
	local board=$(board_name)

	case "$board" in
	nokia,xg-040g-md)
		nokia_initial_setup
		;;
	*)
		;;
	esac
}

RAMFS_COPY_BIN='fitblk fit_check_sign'

REQUIRE_IMAGE_METADATA=1

airoha_require_tcboot_layout()
{
	local ubidev volume

	ubidev="$(nand_find_ubi ubi)"
	[ -n "$ubidev" ] || {
		echo "tcboot UBI is not initialized; restore it through tcboot recovery."
		return 1
	}
	for volume in bosa ri; do
		[ -n "$(nand_find_volume "$ubidev" "$volume")" ] || {
			echo "PON volume $volume is missing; restore its stock backup before upgrading."
			return 1
		}
	done
}

airoha_require_ubi_layout()
{
	local ubidev volume fip_volume

	ubidev="$(nand_find_ubi ubi)"
	[ -n "$ubidev" ] || {
		echo "UBI is not initialized; create the base volumes from U-Boot recovery."
		return 1
	}

	for volume in fip ubootenv ubootenv2 "$@"; do
		if [ -z "$(nand_find_volume "$ubidev" "$volume")" ]; then
			echo "UBI base volume $volume is missing; repair the layout from U-Boot recovery."
			return 1
		fi
	done

	fip_volume="$(nand_find_volume "$ubidev" fip)"
	[ "$(cat "/sys/class/ubi/$fip_volume/data_bytes")" -gt 0 ] || {
		echo "The fip volume does not contain BL31/U-Boot; install the boot chain first."
		return 1
	}
}

platform_check_image() {
	local board=$(board_name)

	[ "$#" -gt 1 ] && return 1

	case "$board" in
	nokia,xg-040g-md-tcboot)
		# Whole-UBI uploads can erase calibration. Accept this profile's tar only.
		tar tf "$1" sysupgrade-nokia_xg-040g-md-tcboot/CONTROL >/dev/null 2>&1 || return 1
		nand_do_platform_check "$board" "$1"
		return $?
		;;
	gemtek,xg2010g|\
	fiberhome,hg5382a|\
	fiberhome,hg5585f-ct|\
	fiberhome,hg5585f-cu|\
	unionman,ung00a|\
	znxt,zn504xg-d|\
	znxt,zn515xg-d|\
	h3c,hm2004-du|\
	nokia,xg-040g-md-ubi|\
	nokia,xg-040g-tf-ubi|\
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
		nokia,xg-040g-md-tcboot)
			CI_UBIPART=ubi
			CI_KERNPART=kernel
			CI_SKIP_KERNEL_MTD=1
			airoha_require_tcboot_layout && nand_do_upgrade "$1"
			;;
		gemtek,w1700k-ubi|\
		quantum,q1000k-ubi)
			fit_do_upgrade "$1"
			;;
		gemtek,xg2010g|\
		fiberhome,hg5382a|\
		fiberhome,hg5585f-ct|\
		fiberhome,hg5585f-cu|\
		unionman,ung00a|\
		znxt,zn504xg-d|\
		znxt,zn515xg-d|\
		h3c,hm2004-du)
			airoha_require_ubi_layout factory && fit_do_upgrade "$1"
			;;
		nokia,xg-040g-md-ubi|\
		nokia,xg-040g-tf-ubi)
			airoha_require_ubi_layout bosa ri && fit_do_upgrade "$1"
			;;
		*)
			nand_do_upgrade "$1"
			;;
	esac
}

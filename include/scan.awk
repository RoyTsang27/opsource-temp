BEGIN { FS="/" }
$1 ~ /^feeds/ { FEEDS[$NF]=$0 }
$1 !~ /^feeds/ { PKGS[$NF]=$0 }
END {
	# Filter-out OpenWrt packages which have a feeds equivalent
	for (pkg in PKGS)
		if (pkg in FEEDS) {
			# Stale PON feed symlinks must not override the audited built-in tree.
			if (PKGS[pkg] ~ /^pon\//) {
				print "Ignoring feed override for integrated PON package " pkg > "/dev/stderr"
				delete FEEDS[pkg]
				continue
			}
			print PKGS[pkg] > of
			delete PKGS[pkg]
		}
	n = asort(PKGS)
	for (i=1; i <= n; i++) {
		print PKGS[i]
	}
	n = asort(FEEDS)
	for (i=1; i <= n; i++){
		print FEEDS[i]
	}
}

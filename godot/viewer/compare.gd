extends SceneTree
## Side-by-side / stacked comparison of two images (e.g. the game's screenshot and a Godot render of the same frame).
##   godot --headless -s res://viewer/compare.gd -- <top.png> <bottom.png> <out.png> [width] [--crop x,y,w,h]
## Both images are scaled to `width` (default 1600) and stacked vertically; --crop (fractions 0..1) cuts the same
## region from both first. Also prints the mean absolute difference per channel (0..255).

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 3:
		print("usage: compare.gd <top.png> <bottom.png> <out.png> [width] [--crop x,y,w,h]")
		quit(2)
		return
	var width := 1600
	var crop := Rect2(0, 0, 1, 1)
	var i := 3
	while i < args.size():
		if args[i] == "--crop" and i + 1 < args.size():
			var p := args[i + 1].split(",")
			crop = Rect2(float(p[0]), float(p[1]), float(p[2]), float(p[3]))
			i += 2
			continue
		width = int(args[i])
		i += 1
	var imgs: Array[Image] = []
	for k in 2:
		var im := Image.load_from_file(args[k])
		if im == null:
			push_error("cannot load " + args[k])
			quit(1)
			return
		im.convert(Image.FORMAT_RGB8)
		var r := Rect2i(int(crop.position.x * im.get_width()), int(crop.position.y * im.get_height()),
			int(crop.size.x * im.get_width()), int(crop.size.y * im.get_height()))
		im = im.get_region(r)
		var h := int(round(float(width) * im.get_height() / im.get_width()))
		im.resize(width, h, Image.INTERPOLATE_LANCZOS)
		imgs.append(im)
	var h0 := imgs[0].get_height()
	var h1 := imgs[1].get_height()
	var out := Image.create(width, h0 + h1 + 4, false, Image.FORMAT_RGB8)
	out.fill(Color(1, 0, 1))
	out.blit_rect(imgs[0], Rect2i(0, 0, width, h0), Vector2i(0, 0))
	out.blit_rect(imgs[1], Rect2i(0, 0, width, h1), Vector2i(0, h0 + 4))
	out.save_png(args[2])
	if h0 == h1:
		var a := imgs[0].get_data()
		var b := imgs[1].get_data()
		var s := [0.0, 0.0, 0.0]
		for j in range(0, a.size(), 3 * 7):
			for c in 3:
				s[c] += absf(a[j + c] - b[j + c])
		var n := float(a.size()) / (3 * 7)
		print("compare: mean |diff| r %.1f g %.1f b %.1f" % [s[0] / n, s[1] / n, s[2] / n])
	print("compare: saved ", args[2])
	quit(0)

import ffmpeg

v_in = ffmpeg.input("test.mp4").video
v = v_in.filter('setpts', 'PTS-STARTPTS')

v_split = v.split()
v_main = v_split[0]
v_bg = v_split[1]

bg = v_bg.filter('scale', 1080, 1920, force_original_aspect_ratio='increase').filter('crop', 1080, 1920).filter('boxblur', luma_radius=40, luma_power=2)
v_main = v_main.filter('scale', width=1080, height=-2)

v_out = ffmpeg.overlay(bg, v_main, x='(W-w)/2', y='(H-h)/2', shortest=1)

print(ffmpeg.compile(ffmpeg.output(v_out, "out.mp4")))

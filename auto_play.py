from dataclasses import dataclass
import sus

with open("chart/chart.sus", "r") as file:
    score = sus.load(file)

TAP_DURATION = 0.02 # タップの時間[sec]
FLICK_DURATION= 0.04 # フリックの時間[sec]
FLICK_OFFSET = 800 # フリックの移動距離

# 画面は10000x10000で表される(1920x1080などの画面サイズが10000×10000に正規化されている)
SCREEN_MIN_X = 1500
SCREEN_MAX_X = 8500
SCREEN_Y = 8000

FLICK_DIVISION_TIME = 0.0166 # 60fps
SLIDE_DIVISION_TICK = 10

# タップノーツ
@dataclass
class TapNote:
    tick: int
    lane: int
    width: int
    type: int

# ディレクショナルノーツ
@dataclass
class DirectionalNote:
    tick: int
    lane: int
    width: int
    type: int

# スライドノーツ
@dataclass
class SlideNote:
    tick: int
    lane: int
    width: int
    type: int # 1:開始, 2:終了, 3:中継点, 5:中継点(不可視)
    mod: int # 0:通常, 1:減速(easeOut), 3:加速(easeIn), 4: 無視
    end_type: int # 0: 終端(通常)もしくは終端ではない, 1: 終端(真上フリック), 2: 使用しない, 3: 終端(左上フリック), 4: 終端(右上フリック)
    id: int

# タッチイベント
@dataclass
class Touch:
    time: float
    touch_id: int
    type: int # 0: start tap and attaching, 1: release
    x: int
    y: int

# 現在のtickから拍子を取得
def get_current_bar_length(tick: int) -> float:
    for i, bar_length in enumerate(score.bar_lengths):
        if tick > bar_length[0]:
            return score.bar_lengths[i-1][1]

# 現在のtickを時間[sec]に変換
def tick_to_sec(tick: int) -> float:
    # BPM beats per minute 60秒間に何拍あるか[拍/分]
    # 60秒 / BPM = 1拍の秒数=4分音符の秒数[sec]
    # bar_length、拍数*bar_length=で1小節の長さになる
    # 480[tick]=4分音符の長さ
    # 1[sec/tick] = 4分音符の秒数 / 480

    # BPM変化なし
    if len(score.bpms) == 1:
        return ( tick / 480 ) * (60 / score.bpms[0][1])
    # BPM変化あり
    bpm_index = 0
    for i, bpm in enumerate(score.bpms):
        if tick > bpm[0]:
            bpm_index = i
        else:
            break
    sec = 0
    for i, bpm in enumerate(score.bpms[:bpm_index]):
        sec += ((score.bpms[i+1][0] - score.bpms[i][0]) / 480) * 60 / score.bpms[i][1]
    sec += ((tick - score.bpms[bpm_index][0])/480) * 60 / score.bpms[bpm_index][1]
    return sec

# 使用可能なタッチIDを格納
available_touch_ids = list(range(0, 10))

# 使えるタッチIDを返す
def available_touch_id() -> int:
    return available_touch_ids.pop(0)

# タッチIDを解放
def release_touch_id(touch_id: int) -> None:
    if touch_id not in available_touch_ids:
        available_touch_ids.append(touch_id)

# laneとwidthからノーツのx座標を取得
def lane_and_width_to_x(lane: int, width: int) -> int:
    return int((lane - 2 + width / 2) / 12 * (SCREEN_MAX_X - SCREEN_MIN_X) + SCREEN_MIN_X)

# ノーツのY座標を取得
def get_y() -> int:
    return SCREEN_Y

# フリックのタッチイベントを生成
def make_flick(start_time: float, touch_id: int, start_x: int, start_y: int, type: int) -> list:
    current_time = start_time + FLICK_DIVISION_TIME
    flick_touch_events = []
    flick_velocity = FLICK_OFFSET / FLICK_DURATION
    while current_time < start_time+FLICK_DURATION:
        if type == 1: # 真上
            flick_touch_events.append(Touch(current_time, touch_id, 0, start_x, start_y-flick_velocity*(current_time-start_time)))
        elif type == 3: # 左上
            flick_touch_events.append(Touch(current_time, touch_id, 0, start_x-flick_velocity*(current_time-start_time), start_y-flick_velocity*(current_time-start_time)))
        elif type == 4: # 右上
            flick_touch_events.append(Touch(current_time, touch_id, 0, start_x+flick_velocity*(current_time-start_time), start_y-flick_velocity*(current_time-start_time)))
        current_time += FLICK_DIVISION_TIME
    return flick_touch_events

 # スライドの曲線を表す関数を取得 t: 絶対的な進行度
def get_easing_function(mod: int):
    if mod == 0:
        return lambda t: t
    elif mod == 1:
        return lambda t: t * t 
    elif mod == 2:
        return lambda t: 1 - (1 - t) ** 2
    else:
        return lambda t: t

tap_notes = [TapNote(note.tick, note.lane, note.width, note.type) for note in score.taps if 2 <= note.lane <= 13] # レーン外のものはfeverなどの制御ノーツなので無視
directional_notes = [DirectionalNote(note.tick, note.lane, note.width, note.type) for note in score.directionals]
slide_notes = [SlideNote(note.tick, note.lane, note.width, note.type, 0, 0, i) for i, slide in enumerate(score.slides) for note in slide]
for slide_note in slide_notes:
    # 減速, 加速を探す
    slide_modifier = list(filter(lambda x: x.tick == slide_note.tick and x.lane == slide_note.lane and x.width == slide_note.width, directional_notes)) # スライドノーツのtickにあるディレクショナルノーツを探す
    if len(slide_modifier) == 0:
        slide_note.mod = 0
    elif slide_modifier[0].type == 2: # 真下振り下ろし
        slide_note.mod = 1 # 減速 easeOut
    elif slide_modifier[0].type in [5, 6]: # 斜め振り下ろし
        slide_note.mod = 2 # 加速 easeIn
    elif slide_note.type == 2 and slide_modifier[0].type == 1: # 真上フリック
        slide_note.end_type = 1
        directional_notes.remove(slide_modifier[0])
    elif slide_note.type == 2 and slide_modifier[0].type == 3: # 左上フリック
        slide_note.end_type = 3
        directional_notes.remove(slide_modifier[0])
    elif slide_note.type == 2 and slide_modifier[0].type == 4: # 右上フリック
        slide_note.end_type = 4
        directional_notes.remove(slide_modifier[0])
    else:
        raise Exception("Unknown slide modifier type: " + str(slide_modifier[0].type))
    # 無視を探す
    slide_ignore = list(filter(lambda x: x.tick == slide_note.tick and x.lane == slide_note.lane and x.width == slide_note.width and slide_note.type in [3, 5] and x.type == 3, tap_notes)) # スライドノーツのtickにあるタップノーツ(フリック)を探す
    if len(slide_ignore) > 0:
        slide_note.mod = 4

# タップノーツのうち、ディレクショナルノーツと同じtick、lane、widthのものを除く
tap_notes = list(filter(lambda x: not any([x.tick == y.tick and x.lane == y.lane and x.width == y.width for y in directional_notes]), tap_notes))
# タップノーツのうち、スライドノーツと同じtick、lane、widthのものを除く
tap_notes = list(filter(lambda x: not any([x.tick == y.tick and x.lane == y.lane and x.width == y.width for y in slide_notes]), tap_notes))
# タップノーツのうち、タイプが1, 2のものだけを残す(3は不可視中継点に使用するので無視)
tap_notes = list(filter(lambda x: x.type in [1, 2], tap_notes))

all_notes = sorted(tap_notes + directional_notes + slide_notes, key=lambda x: x.tick)

touch_events = [] # 全てのタッチイベントを記録する
tmp_release_events = [] # 一時的に保持しておく「離す」タッチイベント、イベントの時間が過ぎたら削除する

for i, note in enumerate(all_notes):
    if type(note) is TapNote:
        touch_id = available_touch_id()
        # print(f"tap {touch_id}")
        x = lane_and_width_to_x(note.lane, note.width)
        y = get_y()
        touch_events.append(Touch(tick_to_sec(note.tick), touch_id, 0, x, y))
        touch_events.append(Touch(tick_to_sec(note.tick) + TAP_DURATION, touch_id, 1, x, y))
        tmp_release_events.append(Touch(tick_to_sec(note.tick) + TAP_DURATION, touch_id, 1, x, y))
    elif type(note) is DirectionalNote:
        if note.type not in [1, 3, 4]:
            continue
        touch_id = available_touch_id()
        # print(f"DirectionalNote {note.type}")
        x = lane_and_width_to_x(note.lane, note.width)
        y = get_y()
        touch_events.append(Touch(tick_to_sec(note.tick), touch_id, 0, x, y))
        touch_events += make_flick(tick_to_sec(note.tick), touch_id, x, y, note.type)
        touch_events.append(Touch(tick_to_sec(note.tick) + FLICK_DURATION, touch_id, 1, x, y))
        tmp_release_events.append(Touch(tick_to_sec(note.tick) + FLICK_DURATION, touch_id, 1, x, y))
    elif type(note) is SlideNote:
        # print(f"SlideNote {touch_id}")
        if note.type == 1: # スライドの開始
            touch_id = available_touch_id()
            current_note = note
            x = lane_and_width_to_x(current_note.lane, current_note.width)
            y = get_y()
            touch_events.append(Touch(tick_to_sec(current_note.tick), touch_id, 0, x, y))
            division_start_tick = current_note.tick
            division_tick = division_start_tick
            division_start_x = x
            devision_slide_note_start_index = i
            easing_function = get_easing_function(current_note.mod)
            while True:
                next_note = all_notes[devision_slide_note_start_index+1]
                if type(next_note) is SlideNote and next_note.id == current_note.id: # もし次のスライドノーツが、同じidのスライドノーツの場合
                    # 無視される中継点以外のノーツを探し、そのノーツのx座標を取得する
                    if current_note.mod != 4: # 現在のノーツが無視される中継点でない場合
                        division_start_tick = current_note.tick # 分割の開始tickを更新
                        division_tick = division_start_tick # 分割のtickを更新、これを次々と更新していく
                        division_start_x = lane_and_width_to_x(current_note.lane, current_note.width) # 分割の開始x座標を更新
                        # 次の無視されない中継点のノーツを探す
                        not_ignore_slide_note = next_note # 一時的に次のノーツを代入
                        for ni_note in all_notes[devision_slide_note_start_index+1:]:
                            if type(ni_note) is SlideNote and ni_note.id == current_note.id and ni_note.mod != 4:
                                not_ignore_slide_note = ni_note # 次の無視されない中継点のノーツを探し、代入
                                break
                        reference_x = lane_and_width_to_x(not_ignore_slide_note.lane, not_ignore_slide_note.width) # 次の無視されない中継点のノーツのx座標を取得
                        reference_tick = not_ignore_slide_note.tick # 次の無視されない中継点のノーツのtickを取得
                    while next_note.tick - division_tick > SLIDE_DIVISION_TICK: # 次のスライドノーツの中継点や終点が, SLIDE_DIVISION_TICKより長い場合
                        division_tick += SLIDE_DIVISION_TICK # 分割のtickをSLIDE_DIVISION_TICK分進める
                        progress = (tick_to_sec(division_tick) - tick_to_sec(division_start_tick)) / (tick_to_sec(reference_tick) - tick_to_sec(division_start_tick)) # 次の無視されない中継点までの、進捗率を計算
                        x = easing_function(progress) * (reference_x - division_start_x) + division_start_x # easing_functionを使って、進捗率に応じたx座標を計算
                        y = get_y()
                        touch_events.append(Touch(tick_to_sec(division_tick), touch_id, 0, x, y))
                    if next_note.type == 2: # スライドの終了
                        x = lane_and_width_to_x(next_note.lane, next_note.width)
                        y = get_y()
                        if next_note.end_type == 0: # スライドの終了が通常の場合
                            touch_events.append(Touch(tick_to_sec(next_note.tick), touch_id, 1, x, y))
                            tmp_release_events.append(Touch(tick_to_sec(next_note.tick), touch_id, 1, x, y))
                        else: # スライドの終了がフリックの場合
                            touch_events += make_flick(tick_to_sec(next_note.tick), touch_id, x, y, next_note.end_type)
                            touch_events.append(Touch(tick_to_sec(next_note.tick) + FLICK_DURATION, touch_id, 1, x, y))
                            tmp_release_events.append(Touch(tick_to_sec(next_note.tick) + FLICK_DURATION, touch_id, 1, x, y))
                        break
                    else: # 中継点
                        progress = (tick_to_sec(next_note.tick) - tick_to_sec(division_start_tick)) / (tick_to_sec(reference_tick) - tick_to_sec(division_start_tick))
                        x = easing_function(progress) * (reference_x - division_start_x) + division_start_x
                        y = get_y()
                        touch_events.append(Touch(tick_to_sec(next_note.tick), touch_id, 0, x, y))
                        if next_note.mod != 4: # 無視される中継点でない場合
                            easing_function = get_easing_function(next_note.mod) # easing_functionを更新
                        devision_slide_note_start_index += 1
                        current_note = next_note
                else:
                    devision_slide_note_start_index += 1

    # 既に終了している「離す」タッチイベントを探す
    remove_release_events = [release_event for release_event in tmp_release_events if release_event.time < tick_to_sec(note.tick)]
    for release_event in remove_release_events:
        tmp_release_events.remove(release_event) # 一時的に保持しておく「離す」タッチイベントから削除する
        release_touch_id(release_event.touch_id) # タッチIDを解放する

touch_events = sorted(touch_events, key=lambda x: x.time) # タッチイベントを時間順にソートする
last_time = touch_events[-1].time # 最後のタッチイベントの時間をlast_timeに代入する

# 最後に画面中央を全ての指でタップする。これがないと、最後にタッチした指が離れないことがある
for touch_id in range(10):
    touch_events.append(Touch(last_time+0.001, touch_id, 1, 0, 0))
    touch_events.append(Touch(last_time+0.002, touch_id, 0, 5000, 5000))
    touch_events.append(Touch(last_time+0.003, touch_id, 1, 0, 0))

event_start_time = touch_events[0].time # タッチイベントの開始時間をevent_start_timeに代入する
for touch_event in touch_events:
    touch_event.time -= event_start_time # タッチイベントの開始時間を0にする
    print(int(touch_event.time*1000), touch_event.touch_id, int(touch_event.x), int(touch_event.y), int(touch_event.type))

# ここから下は, Arduino Leonardo, Pro Microにシリアルで送信するためのコード
import time
import serial
from serial.tools import list_ports

ports = list(list_ports.comports())
port_name = ""
for port in ports:
    if "usb" in port.name:
        port_name = port.name
        break
if port_name == "":
    print("Please select serial port manualy.")
    for port in ports:
        print(f"{port.name}: {port.description}")
    exit(1)
port_name = "/dev/" + port_name
ser = serial.Serial(port_name, 115200)

input("Press Enter to start...")

time_start = time.perf_counter()
touch_index = 0
while True:
    now = time.perf_counter() - time_start
    for touch_event in touch_events[touch_index:]:
        if touch_event.time < now:
            touch_index += 1
            print(f"{touch_event.time} {touch_event.touch_id} {touch_event.x} {touch_event.y} {touch_event.type}")
            ser.write(f"{touch_event.touch_id},{int(touch_event.x)},{int(touch_event.y)},{touch_event.type}\r".encode())
        else:
            break
    if touch_index == len(touch_events):
        break
ser.close()

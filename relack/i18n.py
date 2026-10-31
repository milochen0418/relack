"""English / 繁體中文 for the chat screens. The choice is kept per browser."""

import reflex as rx

ZH = {
    "People": "成員", "Rooms": "房間", "Browse rooms": "瀏覽房間", "Saved & scheduled": "收藏與排程",
    "Notifications": "通知", "Desktop notifications": "桌面通知", "Sound": "提示音",
    "Enable": "開啟", "Turn on": "開啟", "Turn off": "關閉", "On": "開", "Off": "關",
    "Search messages, files, people": "搜尋訊息、檔案、成員",
    "For direct messages, @mentions and replies in your threads.": "私訊、@提及和你參與的討論串有回覆時通知你。",
    "Create New Room": "建立房間", "Room Name": "房間名稱", "Description": "說明", "Private room": "私人房間",
    "Group message": "群組私訊", "Cancel": "取消", "Create Room": "建立", "Save": "儲存", "Delete": "刪除",
    "Add people": "加入成員", "Thread": "討論串", "Search results": "搜尋結果", "Messages": "訊息",
    "Files": "檔案", "Online Users": "線上成員", "No Room Selected": "尚未選擇房間",
    "Choose a room from the sidebar to start chatting.": "從左邊選一個房間開始聊天。",
    "Load earlier messages": "載入更早的訊息", "This is the very beginning of ": "這裡是最早的訊息：",
    "Enter to send · Shift+Enter for a new line · @ to mention": "Enter 送出 · Shift+Enter 換行 · @ 提及",
    "Esc to cancel · Enter to save": "Esc 取消 · Enter 儲存", "Delete message": "刪除訊息",
    "Delete this message for everyone? This can't be undone.": "要為所有人刪除這則訊息嗎？刪除後無法復原。",
    "This message was deleted.": "這則訊息已刪除。", "(edited)": "(已編輯)", "Forward": "轉傳",
    "Forward to": "轉傳到", "Pin to room": "釘選到房間", "Unpin": "取消釘選", "Save for later": "收藏",
    "Remind me in 1 hour": "1 小時後提醒我", "Remind me tomorrow": "明天提醒我", "Copy link": "複製連結",
    "Send later": "稍後傳送", "In 1 hour": "1 小時後", "Tomorrow at 9:00": "明天 9:00",
    "Room settings": "房間設定", "Name": "名稱", "Members": "成員", "Mute this room": "靜音這個房間",
    "Unmute this room": "取消靜音", "Archive room": "封存房間", "Webhooks": "Webhook", "Add": "新增",
    "Pinned messages": "釘選的訊息", "Nothing pinned yet.": "還沒有釘選的訊息。",
    "Saved messages": "收藏的訊息", "Scheduled messages": "排程的訊息", "Nothing here yet.": "這裡還沒有東西。",
    "All rooms": "所有房間", "Join": "加入", "Leave": "離開", "Open": "開啟", "Restore": "還原", "Archived": "已封存",
    "This room is archived.": "這個房間已封存，只能閱讀。", "Set a status": "設定狀態",
    "Pause notifications": "暫停通知", "1 hour": "1 小時", "Until tomorrow": "到明天", "Resume": "恢復",
    "Clear": "清除", "is typing…": "正在輸入…", "Waiting for approval": "等待審核",
    "An administrator needs to approve your account. This page opens by itself when they do.": "管理員核准後，這個頁面會自動打開。",
    "Logout": "登出", "Copy Link": "複製連結", "Signed in as guest": "已訪客登入", "Signed in with Google": "Google 登入",
}


class LangState(rx.State):
    lang: str = rx.LocalStorage("", name="relack_lang")

    @rx.event
    def toggle(self):
        self.lang = "en" if self.lang == "zh" else "zh"

    @rx.event
    def set_lang(self, value: str):
        if not self.lang and value in ("en", "zh"):
            self.lang = value


def T(text: str):
    return rx.cond(LangState.lang == "zh", ZH.get(text, text), text)

WAVES_GAME_ID = 3
PGR_GAME_ID = 2
SERVER_ID = "76402e5b20be2c39f095a152090afddc"
SERVER_ID_NET = "919752ae5ea09c1ced910dd668a63ffb"

# 国际服 serverId 映射 (UID 前缀 -> serverId)
NET_SERVER_ID_MAP = {
    5: "591d6af3a3090d8ea00d8f86cf6d7501",
    6: "6eb2a235b30d05efd77bedb5cf60999e",
    7: "86d52186155b148b5c138ceb41be9650",
    8: "919752ae5ea09c1ced910dd668a63ffb",
    9: "10cd7254d57e58ae560b15d51e34b4c",
}

MAIN_URL = "https://api.kurobbs.com"

# sign
SIGNIN_URL = f"{MAIN_URL}/encourage/signIn/v2"
SIGNIN_TASK_LIST_URL = f"{MAIN_URL}/encourage/signIn/initSignInV2"

# login
LOGIN_URL = f"{MAIN_URL}/user/sdkLogin"
LOGIN_LOG_URL = f"{MAIN_URL}/user/login/log"
REQUEST_TOKEN = f"{MAIN_URL}/aki/roleBox/requestToken"

# refresh
REFRESH_URL = f"{MAIN_URL}/aki/roleBox/akiBox/refreshData"

# bbs
FIND_ROLE_LIST_URL = f"{MAIN_URL}/user/role/findRoleList"
GET_TASK_URL = f"{MAIN_URL}/encourage/level/getTaskProcess"
FORUM_LIST_URL = f"{MAIN_URL}/forum/list"
LIKE_URL = f"{MAIN_URL}/forum/like"
SIGN_IN_URL = f"{MAIN_URL}/user/signIn"
POST_DETAIL_URL = f"{MAIN_URL}/forum/getPostDetail"
SHARE_URL = f"{MAIN_URL}/encourage/level/shareTask"

KURO_VERSION = "3.0.3"
PLATFORM_SOURCE = "ios"
CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"
IOS_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko)  KuroGameBox/3.0.3"
)

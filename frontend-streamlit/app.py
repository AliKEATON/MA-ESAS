'''
"""
Streamlit 前端主应用入口
"""

import streamlit as st

# 页面配置
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化 Session State
if "user" not in st.session_state:
    st.session_state.user = None
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# 未登录时显示登录页
if st.session_state.user is None:
    st.title(f"欢迎使用 {APP_TITLE}")
    st.info("请先登录以使用系统功能")

    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

        if submitted:
            # TODO: 调用登录 API
            st.warning("登录功能开发中...")
else:
    # 已登录：显示主界面
    st.title(APP_TITLE)
    st.write(f"欢迎回来，{st.session_state.user['username']}！")
    st.info("请从左侧导航栏选择功能")
'''

from app_main import main

main()

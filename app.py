import os
import numpy as np
import pandas as pd
import streamlit as st

st.title("LH 데이터 분석 앱")
data_path = "./data"
서울시APT = pd.read_csv(f"{data_path}/서울시_공동주택_1차전처리.csv", encoding="cp949")

st.subheader("서울시 APT 데이터 상위 5개")
st.dataframe(서울시APT.head())

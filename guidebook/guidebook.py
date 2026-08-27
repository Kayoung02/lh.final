import pandas as pd
import streamlit as st


def render_guidebook() -> None:
    st.subheader("분석 안내")
    st.caption("서울 공동주택 단지를 기준으로 사업주체의 구성과 시공사의 공급 이력을 공간·시간 관점에서 비교합니다.")

    st.markdown("#### 이 분석에서 답하려는 질문")
    question1, question2, question3 = st.columns(3)
    question1.metric("1. 공급주체", "누가 공급했는가", "민간 · 공공 · 조합 · 민관 공동")
    question2.metric("2. 시공사", "어디에 시공했는가", "자치구별 시공 이력과 점유율")
    question3.metric("3. 향후 확장", "정비사업의 변화", "시공사 선정 근거를 누적·검증")

    st.markdown("#### 현재 분석 범위")
    scope = pd.DataFrame(
        [
            ["공간 범위", "서울특별시", "자치구 단위 비교 · 단지 위치가 확인되는 경우 지도 표시"],
            ["분석 단위", "공동주택 단지", "개별 세대가 아닌 단지 단위 집계"],
            ["공급주체", "민간 · 공공 · 조합 · 공동 시행", "시행사 표준화 및 검증상태를 함께 관리"],
            ["시공사", "시공능력평가와 단지 시공사", "법인명·과거 사명·약칭을 별칭표로 연결"],
            ["시간 범위", "시공능력평가 2007~2026년", "공동주택은 사용승인연도 기준"],
        ],
        columns=["구분", "범위", "해석 기준"],
    )
    st.dataframe(scope, hide_index=True, use_container_width=True)

    st.markdown("#### 핵심 지표의 읽는 법")
    metric_guide = pd.DataFrame(
        [
            ["공급주체 비중", "세대수 비중 70% + 동수 비중 30%", "대단지와 동 수가 많은 단지의 영향을 함께 반영"],
            ["시공 점유율", "세대수 비중 70% + 동수 비중 30%", "공동시공은 참여사 수만큼 균등 배분"],
            ["시공능력평가액", "건설공사 도급능력 평가 지표", "아파트 매출·실제 계약금액과 동일하지 않음"],
            ["정비사업 시공사", "공시·조합자료 등 검증 근거 기반", "입찰·우선협상과 최종 선정은 구분"],
        ],
        columns=["지표", "계산·정의", "주의할 점"],
    )
    st.dataframe(metric_guide, hide_index=True, use_container_width=True)

    st.markdown("#### 탭별 활용")
    tab1, tab2, tab3 = st.columns(3)
    with tab1:
        st.markdown("**1. 아파트 공급주체 구성·지역분포**")
        st.write("서울 전체와 자치구별로 민간·공공·조합·공동 시행의 비중을 비교합니다.")
    with tab2:
        st.markdown("**2. 시공사 시공능력평가·서울 시공 점유율**")
        st.write("도급순위 변화와 서울 자치구별 시공 이력을 함께 살펴봅니다.")
    with tab3:
        st.markdown("**3. 정비사업 분석 확장 방향**")
        st.write("시공사 선정 근거가 축적되면 정비사업 구역과 기존 시공 이력을 연결합니다.")

    st.info("이 대시보드는 현황 탐색 도구입니다. 특정 지역의 가격, 향후 수주, 브랜드 가치의 인과관계나 결과를 단정하지 않습니다.")

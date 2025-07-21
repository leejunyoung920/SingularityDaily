# 텍스트-시각적 의미 제약 AI 생성 이미지 품질 평가

**원제목:** Text-Visual Semantic Constrained AI-Generated Image Quality Assessment

**요약:** 본 연구는 인공지능 생성 이미지(AGI)의 급속한 발전에 따라 그 질적 평가의 중요성이 증대됨에 따라, 기존의 CLIP이나 BLIP과 같은 교차 모달 모델을 이용한 방법의 한계를 극복하고자 제안된 SC-AGIQA 프레임워크에 대한 것이다.  SC-AGIQA는 텍스트-이미지 일관성과 지각적 왜곡을 종합적으로 평가하기 위해 텍스트-시각적 의미 제약 조건을 활용한다.  핵심 모듈인 TSAM(Text-assisted Semantic Alignment Module)은 다중 모달 대규모 언어 모델(MLLM)을 이용하여 이미지 설명을 생성하고 원래 프롬프트와 비교하여 의미 차이를 해소하고 일관성을 개선하며, FFDPM(Frequency-domain Fine-Grained Degradation Perception Module)은 인간 시각 시스템(HVS)의 특성을 활용하여 주파수 영역 분석과 지각 민감도 가중치를 적용하여 미세한 시각적 왜곡을 정량화하고 세밀한 시각적 품질을 향상시킨다.  실험 결과, SC-AGIQA는 기존 최첨단 방법들을 능가하는 성능을 보였다.  특히, 기존 방법들이 AGI 평가에서 나타나는 의미 불일치와 세부 사항 인식 누락 문제를 효과적으로 해결하였다.  본 연구는 다양한 벤치마크 데이터셋을 사용하여 광범위한 실험을 수행하였으며,  개발된 코드는 공개적으로 제공된다.  PLCC와 SRCC 상관 계수를 통해 성능을 측정하였고,  실험 결과는 시각적 자료와 함께 제시되어 SC-AGIQA의 효과를 명확하게 보여준다.  결론적으로, SC-AGIQA는 AGI의 질적 평가를 위한 효과적이고 신뢰할 수 있는 새로운 프레임워크를 제공한다.

[원문 링크](https://arxiv.org/pdf/2507.10432)

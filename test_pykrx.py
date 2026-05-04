"""market_gate.py 패치 후 실제 pykrx 데이터 테스트"""
# market_gate 모듈을 import하면 matplotlib mock이 자동 적용됨
from market_gate import run_kr_market_gate

print("run_kr_market_gate() 실행 중...")
result = run_kr_market_gate()
print(f"Gate: {result.gate}")
print(f"Score: {result.score}")
print(f"Sectors: {[s.name for s in result.sectors]}")
print(f"Metrics: {result.metrics}")

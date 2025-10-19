python -m green_agent_benchmark.cli \
    --config configs/sixmax_llm_showdown.yaml \
    --output artifacts/sixmax_llm_showdown

python -m green_agent_benchmark.cli \
    --config configs/deepseek/hu_deepseek_vs_deepseek.yaml \
    --output artifacts/deepseek/hu_deepseek_vs_deepseek

python -m green_agent_benchmark.cli \
    --config configs/deepseek/hu_deepseek_vs_deepseek_reasoner.yaml \
    --output artifacts/deepseek/hu_deepseek_vs_deepseek_reasoner

python -m green_agent_benchmark.cli \
    --config configs/deepseek/hu_deepseek_vs_deepseek_aggressive.yaml \
    --output artifacts/deepseek/hu_deepseek_vs_deepseek_aggressive

python -m green_agent_benchmark.cli \
    --config configs/deepseek/hu_deepseek_vs_deepseek_conservative.yaml \
    --output artifacts/deepseek/hu_deepseek_vs_deepseek_conservative

python -m green_agent_benchmark.cli \
    --config configs/gemini/hu_gemini_vs_gemini.yaml \
    --output artifacts/gemini/hu_gemini_vs_gemini

python -m green_agent_benchmark.cli \
    --config configs/gemini/hu_gemini_vs_gemini_pro.yaml \
    --output artifacts/gemini/hu_gemini_vs_gemini_pro

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MDEV_PATH = BASE / "cache" / "models_dev.json"
if not MDEV_PATH.exists():
    MDEV_PATH = BASE / "models_dev.json"
CANDS_PATH = BASE / "cache" / "all_candidates.json"

TIER1_PROVIDERS = [
    "openai", "anthropic", "google", "deepseek", "xai", "mistral", "alibaba",
    "meta", "moonshotai", "zai", "minimax", "cohere", "xiaomi", "stepfun",
    "inception", "tencent-tokenhub", "bailing", "longcat", "volcengine",
    "upstage", "ai21", "perplexity", "arcee", "nvidia", "liquid",
]
TIER2_PROVIDERS = [
    "zhipuai", "alibaba-cn", "minimax-cn", "moonshotai-cn", "stepfun-ai",
    "amazon-bedrock", "azure", "azure-cognitive-services", "google-vertex",
    "google-vertex-anthropic", "openrouter", "huggingface", "togetherai",
    "fireworks-ai", "deepinfra", "groq", "cerebras", "novita-ai",
    "siliconflow", "ollama-cloud", "vercel",
]

# Fine-tune / third-party creators whose explicit vendor prefix MUST override base model family
FINETUNE_VENDORS = {
    "sao10k", "nousresearch", "nous", "thedrummer", "tngtech", "tng",
    "anthracite-org", "alpindale", "gryphe", "neversleep", "eleutherai",
    "allenai", "prime-intellect", "prime intellect", "nex-agi", "nex agi",
    "poolside", "aionlabs", "aion-labs", "deepcogito", "deep cogito",
    "kwaipilot", "morph", "relace", "essentialai", "essential ai",
    "sarvam", "switchpoint", "servicenow", "mbzuai",
}

# Order matters! Specific brands first (xbai before o4, qwen before claude, etc.)
FAMILY_OWNER = [
    (r"\bxbai\b", "metastone", ["openrouter"]),
    (r"\b(qwen|qwq|qvq|wwen)", "alibaba", ["alibaba", "alibaba-cn", "openrouter", "huggingface"]),
    (r"\b(claude|fable|mythos)", "anthropic", ["anthropic"]),
    (r"^(?:opus|sonnet|haiku)[\s\-]*\d", "anthropic", ["anthropic"]),
    (r"\b(gpt|chatgpt|codex)\b|\bo[134](?:[-.\s]|$)", "openai", ["openai"]),
    (r"\b(gemini|gemma|learnlm|paligemma)", "google", ["google", "openrouter", "nvidia", "huggingface"]),
    (r"\bdeepseek", "deepseek", ["deepseek", "openrouter", "huggingface", "togetherai"]),
    (r"\bgrok", "xai", ["xai", "openrouter"]),
    (r"\b(mistral|ministral|mixtral|codestral|devstral|magistral|pixtral|voxtral|leanstral|mathstral|saba)", "mistral", ["mistral", "openrouter"]),
    (r"\b(muse[- ]|llama)", "meta", ["meta", "openrouter", "huggingface", "groq", "togetherai"]),
    (r"\b(kimi|moonshot)", "moonshotai", ["moonshotai", "openrouter"]),
    (r"\b(glm|chatglm|z1-)", "zai", ["zai", "zhipuai", "openrouter"]),
    (r"\bminimax", "minimax", ["minimax", "openrouter"]),
    (r"\b(command-|c4ai|aya-|tiny-aya|north-)", "cohere", ["cohere", "openrouter"]),
    (r"\bmimo", "xiaomi", ["xiaomi", "openrouter"]),
    (r"\bstep[- ]?\d|\bstepaudio", "stepfun", ["stepfun", "stepfun-ai", "openrouter"]),
    (r"\bmercury", "inception", ["inception", "openrouter"]),
    (r"\b(hy3|hy4|hunyuan)", "tencent-tokenhub", ["tencent-tokenhub", "openrouter"]),
    (r"\b(ling[- ]|ring[- ])", "bailing", ["bailing", "openrouter"]),
    (r"\blongcat", "longcat", ["longcat", "openrouter"]),
    (r"\b(doubao|seed[- ]?\d|ui-tars)", "volcengine", ["volcengine", "openrouter"]),
    (r"\bsolar", "upstage", ["upstage", "openrouter"]),
    (r"\bjamba", "ai21", ["ai21", "openrouter"]),
    (r"\b(sonar|r1-1776)", "perplexity", ["perplexity", "openrouter"]),
    (r"\b(trinity|arcee|virtuoso|maestro|afm-)", "arcee", ["arcee", "openrouter"]),
    (r"\bnemotron", "nvidia", ["nvidia", "openrouter"]),
    (r"\blfm|\bliquid", "liquid", ["liquid", "openrouter"]),
    (r"\bnova\b", "amazon-bedrock", ["amazon-bedrock", "openrouter", "vercel"]),
    (r"\b(phi[- ]?\d|mai-)", "microsoft", ["azure-cognitive-services", "azure", "openrouter"]),
    (r"\bgranite", "ibm", ["openrouter", "huggingface"]),
    (r"\bernie", "baidu", ["openrouter", "huggingface"]),
    (r"\b(olmo|molmo|tulu)", "allenai", ["openrouter", "huggingface"]),
    (r"\baion", "aion-labs", ["openrouter"]),
    (r"\bcomposer", "cursor", ["cursor", "openrouter"]),
    (r"\binkling", "thinkingmachines", ["arcee", "openrouter"]),
    (r"\b(hermes|deephermes)", "nousresearch", ["openrouter", "huggingface"]),
    (r"\breka", "reka", ["openrouter"]),
    (r"\bkat[- ]", "kwaipilot", ["openrouter"]),
    (r"\bintellect", "prime-intellect", ["openrouter"]),
    (r"\bsmol", "huggingface", ["huggingface", "openrouter"]),
    (r"\byi[- ]", "01-ai", ["openrouter"]),
    (r"\binternlm|\binternvl", "internlm", ["openrouter", "huggingface"]),
    (r"\bexaone", "lgai", ["openrouter", "huggingface"]),
    (r"\b(cogito|deepcogito)", "deepcogito", ["openrouter"]),
    (r"\b(morph|relace)", "morph", ["openrouter"]),
    (r"\binflection", "inflection", ["openrouter"]),
    (r"\b(k2-think|mbzuai)", "mbzuai", ["openrouter"]),
    (r"\b(apriel|servicenow)", "servicenow", ["openrouter"]),
    (r"\bsarvam", "sarvam", ["openrouter"]),
    (r"\b(essentialai|rnj)", "essentialai", ["openrouter"]),
    (r"\bspark-x", "iflytek", ["openrouter"]),
    (r"\bdots\d", "rednote", ["openrouter"]),
    (r"\bnanbeige", "nanbeige", ["openrouter"]),
    (r"\bswe[- ]\d", "windsurf", ["openrouter"]),
    (r"\b(?:andromeda|aurora|bert[- ]nebulon|elephant|healer|horizon|hunter|optimus|owl|ox|polaris|pony|quasar|sherlock[- ]dash|sonoma[- ]dusk|sonoma[- ]sky|space[- ]bunny|crouton)[- ](?:alpha|beta|aplha)", "openrouter", ["openrouter"]),
    (r"\bopenrouter fusion", "openrouter", ["openrouter"]),
    (r"\btng r1t", "tngtech", ["openrouter"]),
]

MANUAL_OVERRIDES = {
    "chat gpt 5.2": ("openai", "gpt-5.2"),
    "chatgpt 5 thinking extended": ("openai", "gpt-5"),
    "chatgpt-4o (march 2025)": ("openai", "chatgpt-4o-latest"),
    "gpt-5 high (api)": ("openai", "gpt-5"),
    "openai codex mini": ("openai", "codex-mini"),
    "claude 3.5 sonnet": ("anthropic", "claude-3-5-sonnet-20241022"),
    "claude 3.7 sonnet": ("anthropic", "claude-3-7-sonnet"),
    "claude 3.7 thinking sonnet": ("anthropic", "claude-3-7-sonnet"),
    "claude-3-7-sonnet-thinking": ("anthropic", "claude-3-7-sonnet"),
    "claude 4.1 opus": ("anthropic", "claude-opus-4-1"),
    "claude opus 4": ("anthropic", "claude-opus-4-0"),
    "claude sonnet 4": ("anthropic", "claude-sonnet-4-0"),
    "claude 3 opus": ("anthropic", "claude-3-opus-20240229"),
    "claude 3 haiku": ("anthropic", "claude-3-haiku-20240307"),
    "claude 3.5 haiku": ("anthropic", "claude-3-5-haiku-20241022"),
    "claude fable 5.1 max": ("anthropic", "claude-fable-5-1"),
    "fable-5.1": ("anthropic", "claude-fable-5-1"),
    "opus 4.1": ("anthropic", "claude-opus-4-1"),
    "opus 4.5": ("anthropic", "claude-opus-4-5"),
    "opus 4.6": ("anthropic", "claude-opus-4-6"),
    "opus 4.7": ("anthropic", "claude-opus-4-7"),
    "opus-4.7": ("anthropic", "claude-opus-4-7"),
    "opus-4.8": ("anthropic", "claude-opus-4-8"),
    "opus 5": ("anthropic", "claude-opus-5"),
    "opus 5.5": ("anthropic", "claude-opus-5-5"),
    "opus5.5": ("anthropic", "claude-opus-5-5"),
    "sonnet 4.5": ("anthropic", "claude-sonnet-4-5"),
    "sonnet 5": ("anthropic", "claude-sonnet-5"),
    "sonnet 5.5": ("anthropic", "claude-sonnet-5-5"),
    "haiku 5.5": ("anthropic", "claude-haiku-5-5"),
    "anthropic/minimax-m2": ("minimax", "MiniMax-M2"),
    "deepseek 3.1": ("deepseek", "deepseek-v3.1"),
    "deepseek v3": ("deepseek", "deepseek-v3"),
    "deepseek r1": ("deepseek", "deepseek-r1"),
    "deepseek-r1": ("deepseek", "deepseek-r1"),
    "deepseek: r1 0528": ("deepseek", "deepseek-r1-0528"),
    "r1 0528": ("deepseek", "deepseek-r1-0528"),
    "deepseek-chat-v3": ("deepseek", "deepseek-v3"),
    "deepseek-chat-v3-0324": ("deepseek", "deepseek-v3-0324"),
    "glm-5 1.5tb": ("zai", "glm-5"),
    "qwq": ("alibaba", "qwq-32b-preview"),
    "qwq-32b-preview": ("alibaba", "qwq-32b-preview"),
    "qwq via ollama 20gb": ("alibaba", "qwq-32b-preview"),
    "wwen3.6-35b-a3b": ("alibaba", "qwen3.6-35b-a3b"),
    "qwen3.8-flash-next": ("alibaba", "qwen3.8-flash-next"),
    "qwen 3.8 27b": ("alibaba", "qwen3.8-27b"),
    "qwen3.8-27b": ("alibaba", "qwen3.8-27b"),
    "qwen3.6-27b": ("alibaba", "qwen3.6-27b"),
    "qwen2.5-coder-32b-instruct": ("alibaba", "qwen2.5-coder-32b-instruct"),
    "qwen3-coder-flash mlx": ("alibaba", "qwen3-coder-flash"),
    "qwen 3.6-35b-a3b (base)": ("alibaba", "qwen3.6-35b-a3b"),
    "cerebras-llama3.1-70b": ("meta", "llama-3.1-70b-instruct"),
    "cerebras-llama3.1-8b": ("meta", "llama-3.1-8b-instruct"),
    "cerebras-llama-4-scout-17b-16e-instruct": ("meta", "llama-4-scout-17b-16e-instruct"),
    "llama-3.3-70b-instruct": ("meta", "llama-3.3-70b-instruct"),
    "llama 3.3 70b": ("meta", "llama-3.3-70b-instruct"),
    "llama 3.1 405b": ("meta", "llama-3.1-405b-instruct"),
    "llama 4 scout": ("meta", "llama-4-scout-17b-16e-instruct"),
    "llama 4 maverick": ("meta", "llama-4-maverick-17b-128e-instruct"),
    "phi-4": ("microsoft", "phi-4"),
    "gemma-3-27b-it": ("google", "gemma-3-27b-it"),
    "gemma3n:e4b-it-q4_k_m0": ("google", "gemma-3n-e4b-it"),
    "gemma 3n 4b": ("google", "gemma-3n-e4b-it"),
    "google: gemma 3n 4b": ("google", "gemma-3n-e4b-it"),
    "gemma 4 26b-a4b (17.99gb)": ("google", "gemma-4-26b-a4b-it"),
    "gemma 4 26b-a4b-it-qat": ("google", "gemma-4-26b-a4b-it"),
    "gemma 4 31b-it-qat": ("google", "gemma-4-31b-it"),
    "gemini flash 2.0": ("google", "gemini-2.0-flash"),
    "gemini3": ("google", "gemini-3-pro-preview"),
    "gemini-3": ("google", "gemini-3-pro-preview"),
    "gemini 3.0": ("google", "gemini-3-pro-preview"),
    "gemini 3.0 pro": ("google", "gemini-3-pro-preview"),
    "gemini 3.0 pro ga": ("google", "gemini-3-pro-preview"),
    "gemini 1.5 flash 001/002": ("google", "gemini-1.5-flash-002"),
    "amazon nova lite": ("amazon-bedrock", "nova-lite-v1"),
    "amazon nova micro": ("amazon-bedrock", "nova-micro-v1"),
    "amazon nova pro": ("amazon-bedrock", "nova-pro-v1"),
    "nova lite 1.0": ("amazon-bedrock", "nova-lite-v1"),
    "nova micro 1.0": ("amazon-bedrock", "nova-micro-v1"),
    "nova pro 1.0": ("amazon-bedrock", "nova-pro-v1"),
    "nova premier 1.0": ("amazon-bedrock", "nova-premier-v1"),
    "nova 2 lite": ("amazon-bedrock", "nova-2-lite-v1"),
    "amazon nova 2 lite": ("amazon-bedrock", "nova-2-lite-v1"),
    "gpt-4.5": ("openai", "gpt-4.5-preview"),
    "o1-preview": ("openai", "o1-preview"),
    "o1-mini": ("openai", "o1-mini"),
    "o1-pro": ("openai", "o1-pro"),
    "o3": ("openai", "o3"),
    "o3-mini": ("openai", "o3-mini"),
    "o3-pro": ("openai", "o3-pro"),
    "o4-mini": ("openai", "o4-mini"),
    "kimi-k2-instruct-0905": ("moonshotai", "kimi-k2-0905"),
    "kimi k3.1 pro": ("moonshotai", "kimi-k3.1-pro"),
    "kimi k3": ("moonshotai", "kimi-k3"),
    "kimi-3": ("moonshotai", "kimi-k3"),
    "inkling 2 mini": ("thinkingmachines", "inkling-2-mini"),
    "muse ember 1.0": ("meta", "muse-ember-1.0"),
    "muse glimmer": ("meta", "muse-glimmer"),
    "muse wonder": ("meta", "muse-wonder-1.0"),
    "muse wonder full": ("meta", "muse-wonder-1.0"),
    "granite 4.1 3b": ("ibm", "granite-4.1-3b"),
    "hy3-preview": ("tencent-tokenhub", "hy3-preview"),
    "hy4-preview": ("tencent-tokenhub", "hy4-preview"),
    "hy4": ("tencent-tokenhub", "hy4"),
    "hy3": ("tencent-tokenhub", "hy3"),
    "mistral devstral medium": ("mistral", "devstral-medium-latest"),
    "mistral devstral small 1.1": ("mistral", "devstral-small-1.1"),
    "mistral small 3.2 15gb": ("mistral", "mistral-small-3.2-24b-instruct"),
    "nvidia nemotron 3 super": ("nvidia", "nemotron-3-super-120b-a12b"),
    "doubao-seed-pro-2.1": ("volcengine", "doubao-seed-2-1-pro-260628"),
    "xbai o4": ("metastone", "xbai-o4"),
    "crouton aplha": ("openrouter", "crouton-alpha"),
}

SKIP_RAW_NAMES = {
    "claude", "claude opus", "claude render-iterate", "gpt", "gemini", "grok",
    "llama", "qwen", "deepseek", "mistral", "unknown", "other", "test",
    "opus", "fable", "mythos", "wild variant", "deepseek (网页版)", "豆包 (doubao)",
    "gemini 3 checkpoints", "gemini 3 family", "gemini 3.0 latest a/b ckpt",
    "gemini 4", "gpt-6.1", "gpt astra leak", "relay wrappers spoofing gpt-6 astra",
    "qwen3.8 (ollama latest)",
}

VENDOR_NAME_TO_PROV = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "deepseek": "deepseek",
    "deepseek-ai": "deepseek",
    "xai": "xai",
    "x-ai": "xai",
    "x.ai": "xai",
    "mistral": "mistral",
    "mistralai": "mistral",
    "qwen": "alibaba",
    "alibaba": "alibaba",
    "meta": "meta",
    "meta-llama": "meta",
    "moonshotai": "moonshotai",
    "moonshot": "moonshotai",
    "z-ai": "zai",
    "z.ai": "zai",
    "zai": "zai",
    "zai-org": "zai",
    "zhipu": "zai",
    "zhipuai": "zai",
    "minimax": "minimax",
    "minimaxai": "minimax",
    "cohere": "cohere",
    "cohereforai": "cohere",
    "xiaomi": "xiaomi",
    "stepfun": "stepfun",
    "inception": "inception",
    "tencent": "tencent-tokenhub",
    "inclusionai": "bailing",
    "bailing": "bailing",
    "meituan": "longcat",
    "longcat": "longcat",
    "bytedance": "volcengine",
    "bytedance seed": "volcengine",
    "bytedance-seed": "volcengine",
    "volcengine": "volcengine",
    "upstage": "upstage",
    "ai21": "ai21",
    "perplexity": "perplexity",
    "arcee": "arcee",
    "arcee ai": "arcee",
    "arcee-ai": "arcee",
    "nvidia": "nvidia",
    "liquid": "liquid",
    "liquidai": "liquid",
    "amazon": "amazon-bedrock",
    "microsoft": "microsoft",
    "ibm": "ibm",
    "ibm-granite": "ibm",
    "baidu": "baidu",
    "allenai": "allenai",
    "aionlabs": "aion-labs",
    "aion-labs": "aion-labs",
    "nousresearch": "nousresearch",
    "nous": "nousresearch",
    "reka": "reka",
    "01-ai": "01-ai",
    "kwaipilot": "kwaipilot",
    "prime-intellect": "prime-intellect",
    "prime intellect": "prime-intellect",
    "deepcogito": "deepcogito",
    "deep cogito": "deepcogito",
    "inflection": "inflection",
    "morph": "morph",
    "relace": "relace",
    "essentialai": "essentialai",
    "essential ai": "essentialai",
    "sarvam": "sarvam",
    "tng": "tngtech",
    "tngtech": "tngtech",
    "thedrummer": "thedrummer",
    "sao10k": "sao10k",
    "anthracite-org": "anthracite-org",
    "alpindale": "alpindale",
    "switchpoint": "switchpoint",
    "eleutherai": "eleutherai",
    "gryphe": "gryphe",
    "neversleep": "neversleep",
    "nex agi": "nex-agi",
    "nex-agi": "nex-agi",
    "poolside": "poolside",
    "openrouter": None,
    "thudm": "zai",
}


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower().strip())


def norm_dash(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\s_:]+", "-", s)
    s = re.sub(r"[^a-z0-9.\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def strip_quantization(s: str) -> str:
    # Strip parenthetical quantization like (Q4_K_M), (UD-Q4_K_XL), (UD-IQ4_XS), (17.99GB)
    s = re.sub(r"\s*\((?:UD-)?(?:I?Q\d[A-Z0-9_-]*|FP\d+|BF16|NVFP4|\d+(?:\.\d+)?GB)\)\s*$", "", s, flags=re.I).strip()
    # Strip trailing GGUF/EXL/MLX/quantization tags
    s = re.sub(r"[\s_\-]+(?:UD[\s_\-]+)?(?:I?Q\d[_\s-]*[A-Z0-9_]*|GGUF|MLX|AWQ|GPTQ|EXL2|FP8|NVFP4|BF16|4bit|8bit|6bit)(?:\.gguf)?$", "", s, flags=re.I).strip()
    s = re.sub(r"\s*-\s*EXL Quantized.*$", "", s, flags=re.I).strip()
    s = re.sub(r"\s+\d+(?:\.\d+)?GB(?:\s+GGUF)?$", "", s, flags=re.I).strip()
    s = re.sub(r"\.gguf$", "", s, flags=re.I).strip()
    # Ollama colon quantization like Qwen3.8:27b_Q8_0 -> Qwen3.8-27b
    s = re.sub(r":(\d+b)[-_](?:I?Q\d[A-Z0-9_]*)", r"-\1", s, flags=re.I).strip()
    # Strip trailing :free / :exacto / :Q4_K_M etc.
    s = re.sub(r":(?:free|exacto|beta|nitro|floor|I?Q\d[A-Z0-9_]*|BF16|FP16|FP8|NVFP4)\b", "", s, flags=re.I).strip()
    return s


def clean_raw_model(raw: str):
    s = raw.strip()
    s = re.sub(r"（[^）]*）", "", s).strip()
    # Remove trailing effort/test parens ONLY
    s = re.sub(
        r"\s*\((?:xhigh|high|medium|med|low|minimal|none|max|default|no\s*thinking|thinking|reasoning|non-reasoning|extended)\)\s*$",
        "",
        s,
        flags=re.I,
    ).strip()
    # Remove trailing " Thinking" ONLY on Claude Opus/Sonnet/Haiku
    if re.search(r"\bclaude\b", s, re.I) and re.search(r"\s+thinking$", s, re.I):
        s = re.sub(r"\s+thinking$", "", s, flags=re.I).strip()

    s_q = strip_quantization(s)

    wrapper_prefix = re.compile(
        r"^(?:openrouter/|hf\.co/|huggingface\.co/|mlx-community/|unsloth/|gg-hf-gm/|bartowski/|lmstudio-community/|ISTA-DASLab/)",
        re.I,
    )
    s_unwrapped = wrapper_prefix.sub("", s_q).strip()
    s_unwrapped = strip_quantization(s_unwrapped)
    s_unwrapped = re.sub(r"[-_]GSQ-RCO-Coder(?:-GGUF)?$", "", s_unwrapped, flags=re.I).strip()

    explicit_vendor = None
    m_colon = re.match(r"^([A-Za-z0-9 ._-]{2,30}):\s+(.+)$", s_unwrapped)
    if m_colon:
        explicit_vendor = m_colon.group(1).strip()
        model_part = m_colon.group(2).strip()
    elif "/" in s_unwrapped and " " not in s_unwrapped.split("/", 1)[0]:
        parts = s_unwrapped.split("/")
        explicit_vendor = parts[0].strip()
        model_part = "/".join(parts[1:]).strip()
    else:
        model_part = s_unwrapped

    return s, s_unwrapped, explicit_vendor, model_part


def build_mdev_index(mdev: dict):
    by_provider_norm_id = defaultdict(dict)
    by_provider_alnum_id = defaultdict(dict)
    by_provider_norm_name = defaultdict(dict)
    by_submodel_alnum = defaultdict(list)

    tier1_set = {p: i for i, p in enumerate(TIER1_PROVIDERS)}
    tier2_set = {p: 100 + i for i, p in enumerate(TIER2_PROVIDERS)}

    def prov_rank(pid):
        if pid in tier1_set:
            return tier1_set[pid]
        if pid in tier2_set:
            return tier2_set[pid]
        return 1000

    for pid, pinfo in mdev.items():
        rank = prov_rank(pid)
        for mid, mobj in (pinfo.get("models") or {}).items():
            nd = norm_dash(mid)
            nk = norm_key(mid)
            by_provider_norm_id[pid].setdefault(nd, mid)
            by_provider_alnum_id[pid].setdefault(nk, mid)
            leaf = mid.split("/")[-1]
            leaf_no_tag = leaf.split(":")[0]
            by_provider_norm_id[pid].setdefault(norm_dash(leaf_no_tag), mid)
            by_provider_alnum_id[pid].setdefault(norm_key(leaf_no_tag), mid)
            by_submodel_alnum[norm_key(leaf_no_tag)].append((rank, pid, mid, mobj))
            if "/" in mid:
                by_submodel_alnum[norm_key(mid.split(":")[0])].append((rank, pid, mid, mobj))

            name = (mobj.get("name") or "").strip()
            if name:
                clean_name = re.sub(r"^[A-Za-z0-9 ._-]{2,25}:\s+", "", name)
                by_provider_norm_name[pid].setdefault(norm_key(name), mid)
                by_provider_norm_name[pid].setdefault(norm_key(clean_name), mid)
                by_submodel_alnum[norm_key(clean_name)].append((rank, pid, mid, mobj))

    for k in by_submodel_alnum:
        by_submodel_alnum[k].sort(key=lambda x: (x[0], len(x[2])))

    return by_provider_norm_id, by_provider_alnum_id, by_provider_norm_name, by_submodel_alnum


def detect_family_owner(text: str):
    low = text.lower()
    for pat, canon_prov, search_provs in FAMILY_OWNER:
        if re.search(pat, low):
            return canon_prov, search_provs
    return None, None


def find_mdev_match(canon_prov, canon_slug, mdev, idx_tables):
    by_p_nd, by_p_nk, by_p_nm, by_sub = idx_tables
    nd = norm_dash(canon_slug)
    nk = norm_key(canon_slug)
    if canon_prov in mdev:
        mid = by_p_nd[canon_prov].get(nd) or by_p_nk[canon_prov].get(nk)
        if mid:
            return f"{canon_prov}/{mid}", True, mdev[canon_prov]["models"][mid]
    hits = by_sub.get(nk)
    if hits:
        _, pid, mid, mobj = hits[0]
        return f"{pid}/{mid}", (pid == canon_prov), mobj
    return None, False, None


def resolve_model(raw: str, mdev: dict, idx_tables):
    by_p_nd, by_p_nk, by_p_nm, by_sub = idx_tables
    cleaned_full, unwrapped, explicit_vendor, model_part = clean_raw_model(raw)

    low_raw = raw.strip().lower()
    low_full = cleaned_full.lower()
    low_unwrapped = unwrapped.lower()
    low_part = model_part.lower()

    if low_raw in SKIP_RAW_NAMES or low_full in SKIP_RAW_NAMES or low_part in SKIP_RAW_NAMES:
        return None

    # 1. Check MANUAL_OVERRIDES
    for key in (low_raw, low_full, low_unwrapped, low_part):
        if key in MANUAL_OVERRIDES:
            canon_prov, canon_slug = MANUAL_OVERRIDES[key]
            mdev_id, mdev_fp, mdev_obj = find_mdev_match(canon_prov, canon_slug, mdev, idx_tables)
            return {
                "model_id": f"{canon_prov}/{canon_slug}",
                "provider": canon_prov,
                "slug": canon_slug,
                "models_dev_id": mdev_id,
                "models_dev_exact": mdev_id is not None,
                "models_dev_first_party": mdev_fp,
                "match_method": "manual_override",
                "mdev_meta": mdev_obj,
            }

    # 2. Check if explicit_vendor is a known fine-tune/independent creator
    canon_prov, search_provs = None, None
    if explicit_vendor and explicit_vendor.lower() in FINETUNE_VENDORS:
        ev = VENDOR_NAME_TO_PROV.get(explicit_vendor.lower(), norm_dash(explicit_vendor))
        canon_prov = ev
        search_provs = [ev, "openrouter", "huggingface"]
    else:
        canon_prov, search_provs = detect_family_owner(model_part)
        if not canon_prov:
            canon_prov, search_provs = detect_family_owner(unwrapped)
        if not canon_prov and explicit_vendor:
            ev = VENDOR_NAME_TO_PROV.get(explicit_vendor.lower())
            if ev:
                canon_prov = ev
                search_provs = [ev, "openrouter", "huggingface"]

    # Build candidate query strings
    queries = [model_part]
    if canon_prov == "anthropic":
        queries.append(re.sub(r"(\d)\.(\d)", r"\1-\2", model_part))
        if not re.search(r"\bclaude\b", model_part, re.I):
            queries.append("claude-" + re.sub(r"(\d)\.(\d)", r"\1-\2", model_part))
        m_swap = re.match(r"^claude\s+(\d+(?:[.\-]\d+)?)\s+(opus|sonnet|haiku|fable)(.*)$", model_part, re.I)
        if m_swap:
            queries.append(f"claude-{m_swap.group(2)}-{m_swap.group(1).replace('.', '-')}{m_swap.group(3)}")
    elif canon_prov == "volcengine":
        if not model_part.lower().startswith("doubao"):
            queries.append("doubao-" + model_part)
        queries.append(re.sub(r"(\d)\.(\d)", r"\1-\2", model_part))
    elif canon_prov == "alibaba":
        queries.append(re.sub(r"^qwen\s+", "qwen", model_part, flags=re.I))
    elif canon_prov == "nvidia":
        queries.append(re.sub(r"^nvidia[- ]+", "", model_part, flags=re.I))

    # 3. Search authoritative providers first
    if search_provs:
        for sp in search_provs:
            if sp not in mdev:
                continue
            for q in queries:
                nd = norm_dash(q)
                nk = norm_key(q)
                mid = by_p_nd[sp].get(nd) or by_p_nk[sp].get(nk) or by_p_nm[sp].get(nk)
                if mid:
                    leaf = mid.split("/")[-1].split(":")[0]
                    is_fp = (sp == canon_prov)
                    return {
                        "model_id": f"{canon_prov}/{leaf}",
                        "provider": canon_prov,
                        "slug": leaf,
                        "models_dev_id": f"{sp}/{mid}",
                        "models_dev_exact": True,
                        "models_dev_first_party": is_fp,
                        "match_method": f"provider_exact:{sp}",
                        "mdev_meta": mdev[sp]["models"][mid],
                    }

    # 4. Global search across all models.dev providers
    for q in queries:
        nk = norm_key(q)
        hits = by_sub.get(nk)
        if hits:
            rank, pid, mid, mobj = hits[0]
            leaf = mid.split("/")[-1].split(":")[0]
            if canon_prov:
                out_prov = canon_prov
            elif "/" in mid:
                sub_v = mid.split("/")[0].lower()
                out_prov = VENDOR_NAME_TO_PROV.get(sub_v, sub_v)
            else:
                out_prov = pid
            return {
                "model_id": f"{out_prov}/{leaf}",
                "provider": out_prov,
                "slug": leaf,
                "models_dev_id": f"{pid}/{mid}",
                "models_dev_exact": True,
                "models_dev_first_party": (pid == out_prov and pid in TIER1_PROVIDERS),
                "match_method": f"global_exact:{pid}",
                "mdev_meta": mobj,
            }

    # 5. Normalized fallback in models.dev convention
    out_prov = canon_prov
    if not out_prov and explicit_vendor:
        out_prov = VENDOR_NAME_TO_PROV.get(explicit_vendor.lower(), norm_dash(explicit_vendor))
    if not out_prov:
        out_prov = "community"

    slug = norm_dash(model_part)
    if out_prov == "anthropic":
        slug = re.sub(r"(\d)\.(\d)", r"\1-\2", slug)
        if not slug.startswith("claude-"):
            slug = "claude-" + slug
    elif out_prov == "alibaba":
        slug = re.sub(r"^qwen-(\d)", r"qwen\1", slug)
    elif out_prov == "nvidia":
        slug = re.sub(r"^nvidia-", "", slug)

    return {
        "model_id": f"{out_prov}/{slug}",
        "provider": out_prov,
        "slug": slug,
        "models_dev_id": None,
        "models_dev_exact": False,
        "models_dev_first_party": False,
        "match_method": "normalized_fallback",
        "mdev_meta": None,
    }


def main():
    mdev = json.loads(MDEV_PATH.read_text(encoding="utf-8"))
    cands = json.loads(CANDS_PATH.read_text(encoding="utf-8"))
    idx_tables = build_mdev_index(mdev)

    raw_counts = Counter(c["raw_model"] for c in cands)
    mapping = {}
    skipped = []
    for raw in sorted(raw_counts.keys(), key=lambda x: x.lower()):
        res = resolve_model(raw, mdev, idx_tables)
        if res is None:
            skipped.append((raw, raw_counts[raw]))
            continue
        meta = res.pop("mdev_meta")
        if meta:
            res["mdev_name"] = meta.get("name")
            res["mdev_release_date"] = meta.get("release_date")
            res["mdev_family"] = meta.get("family")
            res["mdev_reasoning"] = meta.get("reasoning")
            res["mdev_open_weights"] = meta.get("open_weights")
        else:
            res["mdev_name"] = None
            res["mdev_release_date"] = None
            res["mdev_family"] = None
            res["mdev_reasoning"] = None
            res["mdev_open_weights"] = None
        mapping[raw] = res

    # Resolve any case-only collisions (critical on Windows!) by preferring models_dev_exact casing
    by_lower = defaultdict(list)
    for raw, info in mapping.items():
        by_lower[info["model_id"].lower()].append((raw, info))
    for low_id, entries in by_lower.items():
        distinct = sorted(set(e[1]["model_id"] for e in entries))
        if len(distinct) > 1:
            # Prefer models_dev_first_party, then models_dev_exact, then lowercase
            entries_sorted = sorted(
                entries,
                key=lambda e: (not e[1]["models_dev_first_party"], not e[1]["models_dev_exact"], e[1]["model_id"]),
            )
            winner = entries_sorted[0][1]
            for raw, info in entries:
                info["model_id"] = winner["model_id"]
                info["provider"] = winner["provider"]
                info["slug"] = winner["slug"]
                if not info["models_dev_exact"] and winner["models_dev_exact"]:
                    info["models_dev_id"] = winner["models_dev_id"]
                    info["models_dev_exact"] = True
                    info["models_dev_first_party"] = winner["models_dev_first_party"]

    canon_ids = defaultdict(list)
    for raw, info in mapping.items():
        canon_ids[info["model_id"]].append((raw, info))

    exact_models = sum(1 for cid, rows in canon_ids.items() if any(r[1]["models_dev_exact"] for r in rows))
    fp_models = sum(1 for cid, rows in canon_ids.items() if any(r[1]["models_dev_first_party"] for r in rows))
    fallback_models = [cid for cid, rows in canon_ids.items() if not any(r[1]["models_dev_exact"] for r in rows)]
    comm_models = [cid for cid in sorted(canon_ids) if cid.startswith("community/")]

    print(f"Raw model strings: {len(raw_counts)} -> skipped: {len(skipped)} | mapped: {len(mapping)}")
    print(f"Unique canonical model_ids: {len(canon_ids)}")
    print(f"  Exact match in models.dev: {exact_models} ({exact_models*100/len(canon_ids):.1f}%)")
    print(f"  First-party match in models.dev: {fp_models}")
    print(f"  Normalized fallback (retired/unlisted in live models.dev): {len(fallback_models)}")
    print(f"  Remaining community/* models: {len(comm_models)} -> {comm_models}")

    print("\nProvider distribution (top 30):")
    prov_counts = Counter(cid.split("/")[0] for cid in canon_ids)
    for p, cnt in prov_counts.most_common(30):
        print(f"  {p:24s}: {cnt}")

    out = BASE / "cache" / "model_mapping.json"
    out.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()

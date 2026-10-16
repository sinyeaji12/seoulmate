from seoulmate.config import Settings


def build_llm(s: Settings):
    if s.llm_provider == "openai":
        from seoulmate.clients.openai_llm import OpenAILLM

        return OpenAILLM(s.openai_api_key, s.resolved_model)
    from seoulmate.clients.llm import AnthropicLLM

    return AnthropicLLM(s.anthropic_api_key, s.resolved_model, s.anthropic_workspace_id)

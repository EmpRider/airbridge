# Multi-Provider Support with Intelligent Routing

## Overview
Add multiple premium LLM provider support to [`mcp.py`](../web-screper/mcp.py:1) with intelligent automatic routing based on prompt analysis. The system will analyze the user's prompt and automatically select the best provider based on each provider's specialties.

## Provider Specialties

### Provider Capability Matrix

```json
{
  "providers": {
    "gemini": {
      "specialties": ["reasoning", "deep-thinking", "analysis", "research", "math", "science"],
      "strengths": "Complex reasoning, multi-step problem solving, analytical tasks",
      "url": "https://gemini.google.com/app",
      "selector_input": "[data-placeholder='Ask Gemini']",
      "selector_response": "message-content",
      "priority": 1
    },
    "claude": {
      "specialties": ["coding", "programming", "debugging", "refactoring", "technical-writing"],
      "strengths": "Code generation, debugging, technical documentation, software architecture",
      "url": "https://claude.ai",
      "selector_input": "div[contenteditable='true']",
      "selector_response": "div[data-test-render-count]",
      "priority": 2
    },
    "chatgpt": {
      "specialties": ["planning", "creative-writing", "brainstorming", "general-conversation"],
      "strengths": "Project planning, creative content, ideation, general assistance",
      "url": "https://chat.openai.com",
      "selector_input": "#prompt-textarea",
      "selector_response": ".markdown",
      "priority": 3
    },
    "perplexity": {
      "specialties": ["research", "fact-checking", "web-search", "current-events"],
      "strengths": "Real-time information, web research, fact verification",
      "url": "https://www.perplexity.ai",
      "selector_input": "textarea[placeholder*='Ask']",
      "selector_response": ".prose",
      "priority": 4
    }
  }
}
```

## Architecture Design

### 1. Intelligent Router Component

```python
# providers/router.py

class PromptRouter:
    """Analyzes prompts and routes to best provider"""
    
    def __init__(self, providers_config: dict):
        self.providers = providers_config
        self.keyword_map = self._build_keyword_map()
    
    def _build_keyword_map(self) -> dict:
        """Build keyword -> provider mapping from specialties"""
        keyword_map = {}
        for provider_name, config in self.providers.items():
            for specialty in config['specialties']:
                keywords = self._get_keywords_for_specialty(specialty)
                for keyword in keywords:
                    if keyword not in keyword_map:
                        keyword_map[keyword] = []
                    keyword_map[keyword].append({
                        'provider': provider_name,
                        'priority': config['priority']
                    })
        return keyword_map
    
    def _get_keywords_for_specialty(self, specialty: str) -> list:
        """Map specialty to detection keywords"""
        keyword_patterns = {
            'coding': ['code', 'function', 'class', 'debug', 'implement', 'refactor', 
                      'python', 'javascript', 'java', 'bug', 'error', 'syntax'],
            'reasoning': ['analyze', 'explain', 'why', 'how', 'reason', 'logic', 
                         'think', 'understand', 'complex', 'problem'],
            'planning': ['plan', 'strategy', 'roadmap', 'organize', 'schedule', 
                        'steps', 'approach', 'design'],
            'creative-writing': ['write', 'story', 'article', 'blog', 'content', 
                                'creative', 'draft', 'compose'],
            'research': ['research', 'find', 'search', 'information', 'data', 
                        'study', 'investigate'],
            'math': ['calculate', 'solve', 'equation', 'math', 'formula', 
                    'compute', 'number'],
            'debugging': ['debug', 'fix', 'error', 'bug', 'issue', 'problem', 
                         'not working', 'broken'],
            'web-search': ['latest', 'current', 'news', 'today', 'recent', 
                          'what is', 'who is'],
        }
        return keyword_patterns.get(specialty, [specialty])
    
    def analyze_prompt(self, prompt: str) -> dict:
        """Analyze prompt and return routing decision"""
        prompt_lower = prompt.lower()
        
        # Score each provider
        scores = {}
        for provider_name in self.providers.keys():
            scores[provider_name] = 0
        
        # Keyword matching
        for keyword, providers in self.keyword_map.items():
            if keyword in prompt_lower:
                for provider_info in providers:
                    provider = provider_info['provider']
                    # Higher score for higher priority providers
                    scores[provider] += (5 - provider_info['priority'])
        
        # Pattern-based detection
        scores = self._apply_pattern_rules(prompt_lower, scores)
        
        # Select best provider
        if max(scores.values()) == 0:
            # No clear match, use default (highest priority)
            best_provider = min(self.providers.items(), 
                              key=lambda x: x[1]['priority'])[0]
            confidence = 0.3
        else:
            best_provider = max(scores.items(), key=lambda x: x[1])[0]
            total_score = sum(scores.values())
            confidence = scores[best_provider] / total_score if total_score > 0 else 0
        
        return {
            'provider': best_provider,
            'confidence': confidence,
            'scores': scores,
            'reasoning': self._explain_choice(best_provider, scores)
        }
    
    def _apply_pattern_rules(self, prompt: str, scores: dict) -> dict:
        """Apply pattern-based rules for better detection"""
        
        # Code detection patterns
        if any(x in prompt for x in ['```', 'def ', 'function ', 'class ', 
                                      'import ', 'const ', 'let ', 'var ']):
            scores['claude'] += 10
        
        # Question patterns
        if prompt.startswith(('why ', 'how ', 'what ', 'explain ')):
            scores['gemini'] += 5
        
        # Planning patterns
        if any(x in prompt for x in ['create a plan', 'steps to', 'how to approach']):
            scores['chatgpt'] += 5
        
        # Research patterns
        if any(x in prompt for x in ['latest', 'current', 'as of', 'recent']):
            scores['perplexity'] += 8
        
        # Math/calculation patterns
        if any(x in prompt for x in ['calculate', 'solve', '=', '+', '-', '*', '/']):
            scores['gemini'] += 7
        
        return scores
    
    def _explain_choice(self, provider: str, scores: dict) -> str:
        """Generate human-readable explanation"""
        specialty = self.providers[provider]['strengths']
        return f"Selected {provider} (score: {scores[provider]}) - {specialty}"
    
    def get_fallback_chain(self, primary_provider: str) -> list:
        """Get ordered list of fallback providers"""
        providers = [(name, config['priority']) 
                    for name, config in self.providers.items() 
                    if name != primary_provider]
        providers.sort(key=lambda x: x[1])
        return [p[0] for p in providers]
```

### 2. Updated Provider Base Class

```python
# providers/base.py

from abc import ABC, abstractmethod
from typing import Optional
import asyncio

class BaseProvider(ABC):
    """Base class for all LLM providers"""
    
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get('name', 'unknown')
        self.specialties = config.get('specialties', [])
        self.session = None
        self.is_healthy = True
        self.last_error = None
    
    @abstractmethod
    async def send_prompt(self, prompt: str) -> str:
        """Send prompt and return response"""
        pass
    
    @abstractmethod
    async def initialize_session(self):
        """Initialize browser session"""
        pass
    
    @abstractmethod
    async def cleanup_session(self):
        """Cleanup browser session"""
        pass
    
    async def health_check(self) -> bool:
        """Check if provider is accessible"""
        try:
            # Try to load the page
            if self.session:
                return True
            await self.initialize_session()
            return True
        except Exception as e:
            self.is_healthy = False
            self.last_error = str(e)
            return False
    
    def get_specialties(self) -> list:
        """Return list of specialties"""
        return self.specialties
    
    def get_info(self) -> dict:
        """Return provider information"""
        return {
            'name': self.name,
            'specialties': self.specialties,
            'healthy': self.is_healthy,
            'last_error': self.last_error
        }
```

### 3. Updated MCP Server Integration

```python
# In mcp.py - Updated sections

from providers.router import PromptRouter
from providers.factory import ProviderFactory
from providers.config import load_providers_config

# Global state
PROVIDERS = {}
ROUTER = None
CONFIG = None

async def initialize_providers():
    """Initialize provider system"""
    global ROUTER, CONFIG
    
    CONFIG = load_providers_config()
    ROUTER = PromptRouter(CONFIG['providers'])
    
    logging.info(f"Initialized router with {len(CONFIG['providers'])} providers")

async def ask_provider_auto(prompt: str, force_provider: Optional[str] = None) -> dict:
    """
    Send prompt to automatically selected provider or forced provider
    
    Returns:
        {
            'response': str,
            'provider_used': str,
            'routing_info': dict,
            'fallback_used': bool
        }
    """
    
    # Determine which provider to use
    if force_provider:
        provider_name = force_provider
        routing_info = {'forced': True, 'provider': force_provider}
    else:
        routing_decision = ROUTER.analyze_prompt(prompt)
        provider_name = routing_decision['provider']
        routing_info = routing_decision
        
        logging.info(f"Router decision: {routing_decision['reasoning']}")
    
    # Get or create provider instance
    if provider_name not in PROVIDERS:
        PROVIDERS[provider_name] = await ProviderFactory.create(
            provider_name, 
            CONFIG['providers'][provider_name]
        )
    
    provider = PROVIDERS[provider_name]
    
    # Try primary provider
    try:
        response = await provider.send_prompt(prompt)
        return {
            'response': response,
            'provider_used': provider_name,
            'routing_info': routing_info,
            'fallback_used': False
        }
    except Exception as e:
        logging.error(f"Provider {provider_name} failed: {e}")
        
        # Try fallback chain
        if not force_provider:
            fallback_chain = ROUTER.get_fallback_chain(provider_name)
            for fallback_name in fallback_chain:
                try:
                    logging.info(f"Trying fallback: {fallback_name}")
                    fallback_provider = await ProviderFactory.create(
                        fallback_name,
                        CONFIG['providers'][fallback_name]
                    )
                    response = await fallback_provider.send_prompt(prompt)
                    return {
                        'response': response,
                        'provider_used': fallback_name,
                        'routing_info': routing_info,
                        'fallback_used': True,
                        'original_provider': provider_name
                    }
                except Exception as fallback_error:
                    logging.error(f"Fallback {fallback_name} failed: {fallback_error}")
                    continue
        
        # All providers failed
        raise Exception(f"All providers failed. Last error: {e}")

# Updated MCP tool registration
async def mcp_server():
    # ... existing code ...
    
    # Initialize providers on startup
    await initialize_providers()
    
    # ... rest of server code ...
    
    elif method == "tools/list":
        response["result"] = {
            "tools": [
                {
                    "name": "ask_premium",
                    "description": "Send prompt to premium LLM with automatic provider selection based on task type",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Prompt to send"
                            },
                            "provider": {
                                "type": "string",
                                "description": "Force specific provider (optional). Options: gemini, claude, chatgpt, perplexity",
                                "enum": ["gemini", "claude", "chatgpt", "perplexity"]
                            },
                            "include_routing_info": {
                                "type": "boolean",
                                "description": "Include routing decision details in response",
                                "default": False
                            }
                        },
                        "required": ["prompt"]
                    }
                },
                {
                    "name": "ask_gemini",
                    "description": "Legacy: Send prompt directly to Gemini (use ask_premium instead)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"}
                        },
                        "required": ["prompt"]
                    }
                },
                {
                    "name": "list_providers",
                    "description": "List all available providers and their specialties",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ]
        }
    
    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "ask_premium":
            prompt = arguments.get("prompt", "")
            force_provider = arguments.get("provider")
            include_routing = arguments.get("include_routing_info", False)
            
            result = await ask_provider_auto(prompt, force_provider)
            
            if include_routing:
                response_text = f"{result['response']}\n\n---\nProvider: {result['provider_used']}\nRouting: {result['routing_info']}"
            else:
                response_text = result['response']
            
            response["result"] = {
                "content": [{"type": "text", "text": response_text}]
            }
        
        elif tool_name == "list_providers":
            providers_info = []
            for name, config in CONFIG['providers'].items():
                providers_info.append({
                    'name': name,
                    'specialties': config['specialties'],
                    'strengths': config['strengths'],
                    'priority': config['priority']
                })
            
            response["result"] = {
                "content": [{
                    "type": "text",
                    "text": json.dumps(providers_info, indent=2)
                }]
            }
        
        elif tool_name == "ask_gemini":
            # Legacy support
            prompt = arguments.get("prompt", "")
            result = await ask_provider_auto(prompt, force_provider="gemini")
            response["result"] = {
                "content": [{"type": "text", "text": result['response']}]
            }
```

## Configuration File Structure

```json
{
  "default_provider": "auto",
  "routing": {
    "enabled": true,
    "confidence_threshold": 0.5,
    "fallback_enabled": true
  },
  "providers": {
    "gemini": {
      "enabled": true,
      "name": "gemini",
      "specialties": ["reasoning", "deep-thinking", "analysis", "research", "math", "science"],
      "strengths": "Complex reasoning, multi-step problem solving, analytical tasks",
      "url": "https://gemini.google.com/app",
      "user_data_dir": "edge-gemini-profile",
      "selectors": {
        "input": "[data-placeholder='Ask Gemini']",
        "response": "message-content"
      },
      "priority": 1,
      "timeout": 120
    },
    "claude": {
      "enabled": true,
      "name": "claude",
      "specialties": ["coding", "programming", "debugging", "refactoring", "technical-writing"],
      "strengths": "Code generation, debugging, technical documentation",
      "url": "https://claude.ai",
      "user_data_dir": "edge-claude-profile",
      "selectors": {
        "input": "div[contenteditable='true']",
        "response": "div[data-test-render-count]"
      },
      "priority": 2,
      "timeout": 120
    },
    "chatgpt": {
      "enabled": true,
      "name": "chatgpt",
      "specialties": ["planning", "creative-writing", "brainstorming", "general-conversation"],
      "strengths": "Project planning, creative content, ideation",
      "url": "https://chat.openai.com",
      "user_data_dir": "edge-chatgpt-profile",
      "selectors": {
        "input": "#prompt-textarea",
        "response": ".markdown"
      },
      "priority": 3,
      "timeout": 120
    },
    "perplexity": {
      "enabled": false,
      "name": "perplexity",
      "specialties": ["research", "fact-checking", "web-search", "current-events"],
      "strengths": "Real-time information, web research",
      "url": "https://www.perplexity.ai",
      "user_data_dir": "edge-perplexity-profile",
      "selectors": {
        "input": "textarea[placeholder*='Ask']",
        "response": ".prose"
      },
      "priority": 4,
      "timeout": 120
    }
  }
}
```

## Usage Examples

### Example 1: Automatic Routing - Coding Task
```python
# User prompt: "Debug this Python function that's throwing a KeyError"
# Router detects: keywords=['debug', 'python', 'function', 'error']
# Decision: claude (score: 15) - Code debugging specialist
# Result: Routed to Claude
```

### Example 2: Automatic Routing - Reasoning Task
```python
# User prompt: "Explain why quantum entanglement doesn't violate causality"
# Router detects: keywords=['explain', 'why', 'quantum']
# Decision: gemini (score: 12) - Deep reasoning specialist
# Result: Routed to Gemini
```

### Example 3: Forced Provider
```python
# User prompt: "Write a blog post" + provider="chatgpt"
# Router: Bypassed (forced)
# Result: Routed to ChatGPT
```

### Example 4: Fallback Chain
```python
# User prompt: "Solve this math problem"
# Primary: gemini (fails - timeout)
# Fallback 1: claude (fails - not available)
# Fallback 2: chatgpt (success)
# Result: Response from ChatGPT with fallback flag
```

## Implementation Phases

### Phase 1: Core Routing System ✓
- [x] Design provider capability matrix
- [x] Create PromptRouter class
- [x] Implement keyword-based detection
- [x] Add pattern-based rules

### Phase 2: Provider Integration
- [ ] Refactor existing [`ask_gemini()`](../web-screper/mcp.py:58) into GeminiProvider
- [ ] Implement ClaudeProvider
- [ ] Implement ChatGPTProvider
- [ ] Implement PerplexityProvider (optional)

### Phase 3: MCP Server Updates
- [ ] Add `ask_premium` tool with auto-routing
- [ ] Add `list_providers` tool
- [ ] Maintain `ask_gemini` for backward compatibility
- [ ] Add routing info to responses

### Phase 4: Advanced Features
- [ ] Implement fallback chain
- [ ] Add provider health monitoring
- [ ] Add routing analytics/logging
- [ ] Implement confidence threshold tuning

### Phase 5: Testing & Optimization
- [ ] Test routing accuracy across prompt types
- [ ] Optimize keyword patterns
- [ ] Add routing decision explanations
- [ ] Performance testing

## Benefits

✅ **Intelligent Selection** - Automatically picks best provider for each task
✅ **Transparent** - Users can see which provider was selected and why
✅ **Flexible** - Can force specific provider when needed
✅ **Resilient** - Automatic fallback if primary provider fails
✅ **Extensible** - Easy to add new providers with specialties
✅ **Backward Compatible** - Legacy `ask_gemini` still works

## Testing Strategy

### Routing Accuracy Tests
```python
test_cases = [
    ("Write a Python function to sort a list", "claude"),
    ("Explain the theory of relativity", "gemini"),
    ("Create a project plan for a mobile app", "chatgpt"),
    ("What are the latest AI developments?", "perplexity"),
    ("Debug this JavaScript error", "claude"),
    ("Solve this calculus problem", "gemini"),
]

for prompt, expected_provider in test_cases:
    decision = router.analyze_prompt(prompt)
    assert decision['provider'] == expected_provider
```

## File Structure

```
web-screper/
├── mcp.py                          # Main MCP server (updated)
├── main.py                         # Test script
├── providers/
│   ├── __init__.py                # Provider exports
│   ├── base.py                    # BaseProvider class
│   ├── router.py                  # PromptRouter class
│   ├── factory.py                 # ProviderFactory
│   ├── config.py                  # Configuration loader
│   ├── gemini.py                  # GeminiProvider
│   ├── claude.py                  # ClaudeProvider
│   ├── chatgpt.py                 # ChatGPTProvider
│   └── perplexity.py              # PerplexityProvider (optional)
└── config/
    └── providers.json             # Provider configuration
```

## Next Steps

1. Review and approve this architectural plan
2. Start with Phase 1: Implement PromptRouter
3. Test routing logic with sample prompts
4. Proceed to Phase 2: Provider implementations
5. Integrate with MCP server
6. Test end-to-end functionality

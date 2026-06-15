from langgraph.graph import END, START, StateGraph

from agents.interview_agent.tools import generate_questions_tool, score_answers_tool
from graph.state import AgentState

graph_builder = StateGraph(AgentState)

graph_builder.add_node("generate_questions_tool", generate_questions_tool)
graph_builder.add_node("score_answers_tool", score_answers_tool)

# For now both tools are independent entry points that terminate the graph.
# generate_questions_tool -> score_answers_tool will be wired once the Voice
# Agent subagent sits between them (see .claude/agent-architecture.md).
graph_builder.add_edge(START, "generate_questions_tool")
graph_builder.add_edge("generate_questions_tool", END)
graph_builder.add_edge("score_answers_tool", END)

interview_graph = graph_builder.compile()

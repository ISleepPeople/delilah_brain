from typing import TypedDict
from langgraph.graph import StateGraph, END

# Define the "state" our graph passes around
class State(TypedDict):
    input: str
    output: str

# Simple node that just echoes the input
def echo_node(state: State) -> State:
    return {
        "input": state["input"],
        "output": f"Hello from LangGraph, you said: {state['input']}"
    }

# Build the graph
builder = StateGraph(State)
builder.add_node("echo", echo_node)
builder.set_entry_point("echo")
builder.add_edge("echo", END)

graph = builder.compile()

if __name__ == "__main__":
    result = graph.invoke({"input": "test message"})
    print(result)

from __future__ import annotations

from pathlib import Path

from agent_layer.graphs import WorkloadOptimizationGraph
from agent_layer.graphs.checkpoints import SQLiteCheckpointStore
from judge_layer.simulator import SimulatorEnvironment, load_benchmark


def test_workload_graph_repairs_and_persists_final_checkpoint(tmp_path: Path) -> None:
    case = load_benchmark(Path("judge_layer/benchmarks/07_hidden_path"))
    with SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite") as checkpoints:
        graph = WorkloadOptimizationGraph(
            trajectory_directory=tmp_path / "trajectories",
            checkpointer=checkpoints.saver,
        )
        result = graph.run(
            SimulatorEnvironment(case),
            run_id="checkpoint-run",
            workload_id="payment-service",
            task_id="task-payment",
            context_ref="context://payment-service/abc",
        )
        snapshot = checkpoints.saver.get_tuple(
            {"configurable": {"thread_id": "checkpoint-run:payment-service"}}
        )

    assert result.accepted
    assert result.repair_iterations == 1
    assert snapshot is not None
    assert snapshot.checkpoint["channel_values"]["graph_node"] == "PUBLISH_RESULT_EVENT"

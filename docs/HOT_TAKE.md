# Core insight

> Runtime observation alone does not produce least privilege. It produces least
> observed privilege. Verification turns observation into a safer
> least-privilege workflow.

The current simulator evidence supports this statement within the benchmark's
scope: observed-only policies preserved all declared behavior in 3 of 10 cases,
while Kuber's verified/repaired policies preserved it in 10 of 10. The baseline
actually achieved slightly greater raw reduction because it removed required
permissions; VRR correctly assigns those broken cases zero.

This is evidence for the workflow, not proof for arbitrary applications.
Coverage remains bounded by developer-provided verification.


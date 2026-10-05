# Final report: fastest measured reference study

Best validated combination: original4750000 model plus10percent transition toward the fastest measured path. Full fastest path failed; trained candidates not adopted. No sub150-second lap achieved.

| Run | Valid laps | Completed/attempts | Best s | Median s |
|---|---:|---:|---:|---:|
| baseline | 6 | 3/3 | 150.7315358940541 | 150.78431471870863 |
| baseline_timing | 6 | 3/3 | 150.736818838428 | 150.74466133474925 |
| fastest_line_screen | 0 | 0/3 | None | None |
| eval2500_original | 6 | 3/3 | 150.66831249411916 | 150.7694532935202 |
| eval2500_fastest | 0 | 0/3 | None | None |
| diagnostic_original_curvature | 0 | 0/3 | None | None |
| screen_curriculum10 | 6 | 3/3 | 150.591190259438 | 150.65279251008178 |
| eval2500_curriculum10 | 4 | 2/3 | 150.62330809549894 | 150.67460409915657 |
| baseline_recheck_final | 6 | 3/3 | 150.7189838741324 | 150.7823676220869 |
| curriculum10_fixed_recheck | 6 | 3/3 | 150.58580363501096 | 150.6405894702766 |
| verify_curriculum10_5x2 | 10 | 5/5 | 150.5772173301375 | 150.61508993967436 |
| endurance_curriculum10_8 | 8 | 1/1 | 150.572890105861 | 150.64439396798844 |

## Measured gains

Five-by-two verification:10valid/5of5,median150.615090,0.167278s faster than recent baseline150.782368 (0.129571s versus the faster earlier timingbaseline). Eight-lap endurance:8valid/1of1,median150.644394,best150.572890. New best improves the source150.667138 by0.094248s. These are sequential limited samples, not a confidence interval. All reported lap times use audited complete physical laps; historicalBestLap and training laps excluded.

## Adopted and rejected

Retain original4750000 checkpoint; adopt the isolated10percent reference combination documented in BEST_COMBINATION.json. Global historical defaults and original reference remain preserved. User-requested fulltrace is preserved in reference_lines/fastest_valid_lap.csv but not selected for driving: fixedmodel0/3 and fresh10000+online2500model0/3. The10percent trainedcandidate completed2/3 versus fixedcandidate3/3 and was rejected. No5000extension because training acceptance failed. Bottom/chassis settings untouched. Game display line was not synchronized with training CSV.

## Diagnostics and limitations

New telemetry records command start/end and host observation age alongside existing absolute and relative actions. Hostage p99 approximately5.4ms in both initial reference screens; this does not measure full simulator latency or establish causality. New-line training has more near-limit steering, but trajectory coverage differs, so aggregate fractions cannot assign cause. Original-curvature substitution with fastestgeometry also failed0/3; changing curvature alone was insufficient. Source trajectory shifts lateral observation towardzero when used asreference; learned-offset sensitivity remains a hypothesis.

Steering repeated-motion screen:10percentline352/450 vsoriginal340/450 windows. Faster laps do not demonstrate reduced steering oscillation. Geometry minimum0.542m clearance is local point projection, not full swept-car proof. Reset remains in-place, so initialization differs. No claim of completed causal latency diagnosis or optimal racing-line construction. Historical15k-to20k actor/critic drift analysis was not completed. Instrumentation syntax compiled and ran successfully, but dedicated automated timing tests were not added.

## Next development

1. Preserve this verified combination as the next baseline; test small line-transition increments with matched original4750000 evaluations before training.
2. Fix reproducible start conditions and quantify matched-distance steering response and absolute command lag. Diagnose policy reversals separately from required cornering.
3. Analyze historical actor/critic drift offline and use one-variable learning-rate/update-ratio trials with independent early-stop evals. Do not assume more updates help.
4. Full fastest-path adaptation remains unachieved; dynamically feasible line/speed planning and chassis work remain deferred.

## Reproduction and closeout

BEST_COMBINATION.json identifies the immutable original checkpoint, exact reference, verification config and hashes. Use the verification/endurance config as a template with a fresh output directory. All checkpoints/replays preserved. All experiment clients had exited; explicit controls released. No new experiments scheduled for this window.

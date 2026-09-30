import unittest

from research_relay import context


def limits(ceiling=1_000_000, **policy):
    return context.thresholds({"context_window": ceiling, **policy})


class ThresholdTests(unittest.TestCase):
    def test_defaults_by_ceiling(self):
        # 75% from 400K up; below that the 100K reserve decides.
        table = {1_000_000: (750_000, 200_000), 760_000: (570_000, 152_000), 400_000: (300_000, 80_000),
                 200_000: (100_000, 40_000), 128_000: (28_000, 25_600)}
        for ceiling, (final, step) in table.items():
            with self.subTest(ceiling=ceiling):
                self.assertEqual(limits(ceiling), {"ceiling": ceiling, "final": final, "step": step})

    def test_window_sources_and_compact_limit(self):
        # An explicit policy window beats the transcript's; a null one falls through to it.
        self.assertEqual(context.thresholds({"context_window": 400_000}, 1_000_000)["ceiling"], 400_000)
        self.assertEqual(context.thresholds({"context_window": None}, 760_000)["final"], 570_000)
        self.assertEqual(context.thresholds({"compact_limit": 600_000}, 760_000),
                         {"ceiling": 600_000, "final": 450_000, "step": 120_000})
        self.assertEqual(context.thresholds({"compact_limit": 900_000}, 760_000)["ceiling"], 760_000)

    def test_no_window_or_no_room_means_no_thresholds(self):
        self.assertIsNone(context.thresholds({}))
        self.assertIsNone(context.thresholds({"compact_limit": 600_000}))
        self.assertIsNone(limits(100_000))
        self.assertEqual(limits(100_000, reserve=20_000)["final"], 75_000)

    def test_stored_settings_are_used(self):
        # A file from before modes existed keeps its fraction; the reserve and step defaults apply.
        self.assertEqual(limits(1_000_000, warn_fraction=0.6)["final"], 600_000)
        self.assertEqual(limits(1_000_000, checkpoint_fraction=0)["step"], 0)


class ObserveTests(unittest.TestCase):
    def run_trace(self, trace, state=None, **policy):
        state = {} if state is None else state
        return [context.observe(state, used, limits(**policy)) for used in trace], state

    def test_checkpoints_count_growth_from_the_first_observation(self):
        results, state = self.run_trace([100_000, 250_000, 300_000, 300_000, 520_000])
        self.assertEqual(results, [None, None, ("checkpoint", 200_000), None, ("checkpoint", 220_000)])
        self.assertEqual((state["baseline"], state["final_sent"]), (520_000, False))

    def test_final_once_then_a_reminder_every_step(self):
        results, _ = self.run_trace([560_000, 780_000, 790_000, 979_000, 980_000])
        # 780K is both a step of growth and past the threshold: the final reminder replaces the checkpoint.
        self.assertEqual(results, [None, ("final", 780_000), None, None, ("checkpoint", 200_000)])
        self.assertEqual(self.run_trace([800_000])[0], [("final", 800_000)])  # a fork that starts past it

    def test_drop_without_a_compaction_event(self):
        # The baseline follows usage down; only a drop of a tenth of the ceiling below final re-arms.
        results, _ = self.run_trace([800_000, 700_000, 760_000, 900_000])
        self.assertEqual(results, [("final", 800_000), None, None, ("checkpoint", 200_000)])
        results, _ = self.run_trace([800_000, 640_000, 750_000])
        self.assertEqual(results, [("final", 800_000), None, ("final", 750_000)])

    def test_checkpoints_off_leaves_only_the_final_reminder(self):
        results, _ = self.run_trace([740_000, 760_000, 990_000, 640_000, 760_000], checkpoint_fraction=0)
        self.assertEqual(results, [None, ("final", 760_000), None, None, ("final", 760_000)])

    def test_replaced_context_starts_over(self):
        _, state = self.run_trace([800_000])
        state.update(last_usage={"used": 800_000}, told={"mode": "trajectory"})
        context.replaced(state)
        self.assertEqual(state, {"told": {"mode": "trajectory"}})
        # A compaction that lands just under the threshold still gets its own final reminder.
        self.assertEqual(self.run_trace([700_000, 750_000], state)[0], [None, ("final", 750_000)])


if __name__ == "__main__":
    unittest.main()

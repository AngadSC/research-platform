import type { TestId } from "@/lib/stats/contract";

const QUESTIONS: { q: string; test: TestId }[] = [
  { q: "What do my numbers look like?", test: "describe" },
  { q: "How many of each category are there?", test: "frequencies" },
  { q: "Are my numbers roughly normal?", test: "normality" },
  { q: "Is the average different from a set value?", test: "t_one_sample" },
  { q: "Are two groups different?", test: "t_independent" },
  { q: "Are two groups different, and the numbers are not normal?", test: "mann_whitney" },
  { q: "Did scores change from before to after?", test: "t_paired" },
  { q: "Did scores change, and the numbers are not normal?", test: "wilcoxon" },
  { q: "Are three or more groups different?", test: "anova_oneway" },
  { q: "Are three or more groups different, and the numbers are not normal?", test: "kruskal" },
  { q: "Do two things together affect a number?", test: "anova_twoway" },
  { q: "Are two categories related?", test: "chi_square" },
  { q: "Are two numbers related?", test: "correlation" },
  { q: "What predicts a number?", test: "linear_regression" },
  { q: "What predicts a yes or no outcome?", test: "logistic_regression" },
];

export function TestGuide({ onPick }: { onPick: (test: TestId) => void }) {
  return (
    <details className="rounded-md border p-3">
      <summary className="cursor-pointer text-sm font-medium">Which test should I use?</summary>
      <ul className="mt-2 grid gap-1">
        {QUESTIONS.map(({ q, test }) => (
          <li key={test}>
            <button
              type="button"
              onClick={() => onPick(test)}
              className="text-left text-sm text-primary hover:underline"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

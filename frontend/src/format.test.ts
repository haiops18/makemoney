import { expect, test } from "vitest";
import { formatUsd } from "./format";

test("formats verified USD amounts without inventing missing data", () => {
  expect(formatUsd("45.25")).toBe("$45.25");
  expect(formatUsd(undefined)).toBe("No verified data");
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ImageEvidence, matchingBoxes } from "./ImageEvidence";

afterEach(cleanup);
const locator = {
  width: 2000,
  height: 1000,
  boxes: [
    { text: "BCNF:", x: 400, y: 200, width: 120, height: 40 },
    { text: "Superkey", x: 550, y: 200, width: 120, height: 40 },
  ],
};

it("renders source coordinates in a scalable overlay and allows hiding them", () => {
  render(
    <ImageEvidence
      src="/api/v1/assets/1"
      name="notes.png"
      query="BCNF"
      locator={locator}
    />,
  );
  const overlay = screen.getByRole("img", { name: "Matching words in image" });
  expect(overlay).toHaveAttribute("viewBox", "0 0 2000 1000");
  expect(overlay.querySelector("rect")).toHaveAttribute("x", "400");
  expect(screen.getByText("1 matching word")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Hide highlights" }));
  expect(
    screen.queryByRole("img", { name: "Matching words in image" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show highlights" }));
  expect(
    screen.getByRole("img", { name: "Matching words in image" }),
  ).toBeInTheDocument();
});

it("does not draw invented matches or unscaled boxes from older locators", () => {
  expect(matchingBoxes(locator, "unknownword")).toEqual([]);
  expect(matchingBoxes({ boxes: locator.boxes }, "BCNF")).toEqual([]);
  expect(matchingBoxes(locator, "bcn")).toEqual([]);
});

it("clips bounds, ignores malformed boxes, and deduplicates overlapping chunk metadata", () => {
  const box = { text: "BCNF", x: -5, y: 990, width: 30, height: 30 };
  const result = matchingBoxes(
    { ...locator, boxes: [box, box, { ...box, x: NaN }, { ...box, x: 3000 }] },
    "BCNF",
  );
  expect(result).toEqual([
    { text: "BCNF", x: 0, y: 990, width: 25, height: 10 },
  ]);
});

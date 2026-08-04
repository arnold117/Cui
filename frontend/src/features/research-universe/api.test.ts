import { describe, expect, it } from "vitest"
import { command } from "./api"

describe("native command envelopes", () => {
  it("retains the identical envelope for a transport retry", () => {
    const first = command({ text: "a claim" }, 7)
    const retry = command({ text: "a claim" }, 7, first)
    expect(retry).toEqual(first)
  })
  it("creates a new envelope for a later distinct intent after success", () => {
    const completed = command({ text: "first" }, 7)
    // A definitive success clears the component-held envelope; the next intent has none to retain.
    const next = command({ text: "second" }, 8)
    expect(next.command_id).not.toBe(completed.command_id)
    expect(next).toMatchObject({ text: "second", expected_sequence: 8 })
  })
})

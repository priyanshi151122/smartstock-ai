import { describe, expect, it } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";
import { toApiError } from "../lib/api";

function makeAxiosError(status: number, body: unknown): AxiosError {
  const error = new AxiosError("Request failed");
  error.response = {
    status,
    statusText: "error",
    data: body,
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  };
  return error;
}

describe("toApiError", () => {
  it("extracts the structured backend message", () => {
    const error = toApiError(
      makeAxiosError(422, {
        error: {
          status: 422,
          message: "No valid rows were available to import.",
          issues: [{ field: "quantity", message: "must be a number" }],
        },
      }),
    );
    expect(error.status).toBe(422);
    expect(error.message).toMatch(/No valid rows/);
    expect(error.issues?.[0].field).toBe("quantity");
  });

  it("falls back to a generic message with the status code", () => {
    const error = toApiError(makeAxiosError(503, {}));
    expect(error.status).toBe(503);
    expect(error.message).toMatch(/status 503/);
  });

  it("explains network failures actionably", () => {
    const error = toApiError(new AxiosError("Network Error", "ERR_NETWORK"));
    expect(error.message).toMatch(/backend running on port 8000/);
  });

  it("handles unknown errors without throwing", () => {
    expect(toApiError("boom").message).toBe("Unexpected error.");
    expect(toApiError(new Error("plain")).message).toBe("plain");
  });
});

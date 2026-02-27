import { fireEvent, render, screen } from "@testing-library/react";

import ConfirmationModal from "./ConfirmationModal";

describe("ConfirmationModal", () => {
  it("calls onCancel when overlay is clicked", () => {
    const onCancel = vi.fn();

    render(
      <ConfirmationModal
        isOpen
        title="Delete item"
        message="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByLabelText("Close confirmation modal"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button is clicked", () => {
    const onCancel = vi.fn();

    render(
      <ConfirmationModal
        isOpen
        title="Delete item"
        message="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("does not close when modal content is clicked", () => {
    const onCancel = vi.fn();

    render(
      <ConfirmationModal
        isOpen
        title="Delete item"
        message="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("dialog"));

    expect(onCancel).not.toHaveBeenCalled();
  });
});

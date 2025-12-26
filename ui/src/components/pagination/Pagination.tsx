import styles from "./Pagination.module.css";

export type PaginationProps = {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems: number;
  itemsPerPage: number;
};

export default function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  totalItems,
  itemsPerPage,
}: PaginationProps) {
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const endItem = Math.min(currentPage * itemsPerPage, totalItems);

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  };

  const handleFirst = () => {
    onPageChange(1);
  };

  const handleLast = () => {
    onPageChange(totalPages);
  };

  // Generate page numbers to display
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const maxVisiblePages = 7;

    if (totalPages <= maxVisiblePages) {
      // Show all pages if total pages is less than max visible
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Always show first page
      pages.push(1);

      if (currentPage > 3) {
        pages.push("...");
      }

      // Show pages around current page
      const startPage = Math.max(2, currentPage - 1);
      const endPage = Math.min(totalPages - 1, currentPage + 1);

      for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
      }

      if (currentPage < totalPages - 2) {
        pages.push("...");
      }

      // Always show last page
      pages.push(totalPages);
    }

    return pages;
  };

  if (totalPages <= 1) {
    return null;
  }

  return (
    <div className={styles.pagination_container}>
      <div className={styles.pagination_info}>
        Showing {startItem} - {endItem} of {totalItems} items
      </div>

      <div className={styles.pagination_controls}>
        <button
          className={styles.pagination_button}
          onClick={handleFirst}
          disabled={currentPage === 1}
          aria-label="First page"
        >
          ««
        </button>

        <button
          className={styles.pagination_button}
          onClick={handlePrevious}
          disabled={currentPage === 1}
          aria-label="Previous page"
        >
          «
        </button>

        {getPageNumbers().map((page, index) =>
          page === "..." ? (
            <span key={`ellipsis-${index}`} className={styles.pagination_ellipsis}>
              ...
            </span>
          ) : (
            <button
              key={page}
              className={`${styles.pagination_button} ${
                page === currentPage ? styles.active : ""
              }`}
              onClick={() => onPageChange(page as number)}
            >
              {page}
            </button>
          )
        )}

        <button
          className={styles.pagination_button}
          onClick={handleNext}
          disabled={currentPage === totalPages}
          aria-label="Next page"
        >
          »
        </button>

        <button
          className={styles.pagination_button}
          onClick={handleLast}
          disabled={currentPage === totalPages}
          aria-label="Last page"
        >
          »»
        </button>
      </div>
    </div>
  );
}


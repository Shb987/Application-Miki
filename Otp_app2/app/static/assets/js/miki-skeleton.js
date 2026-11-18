/**
 * MIKI Admin Dashboard - Reusable Loading Skeleton & State Component Library
 * Theme: Primary #603CD8 | Secondary #C44ECC
 */

(function (window, document) {
    'use strict';

    const MikiSkeleton = {
        /**
         * Renders HTML for a set of shimmering KPI stat cards
         * @param {number} count Number of cards (default 4)
         * @returns {string} HTML string
         */
        renderCardsSkeleton: function (count = 4) {
            const colClass = count <= 3 ? 'col-xl-4 col-md-6 mb-3' : 'col-xl-3 col-sm-6 mb-3';
            let html = '<div class="row g-3">';
            for (let i = 0; i < count; i++) {
                html += `
                    <div class="${colClass}">
                        <div class="miki-skeleton-card kpi-card">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <div class="miki-skeleton-box squircle"></div>
                                <div class="miki-skeleton-bar" style="width: 68px; height: 22px; border-radius: 12px;"></div>
                            </div>
                            <div class="miki-skeleton-bar mb-2" style="width: 100px; height: 34px;"></div>
                            <div class="miki-skeleton-bar" style="width: 130px; height: 14px;"></div>
                        </div>
                    </div>
                `;
            }
            html += '</div>';
            return html;
        },

        /**
         * Renders HTML for table body rows with shimmering cells
         * @param {number} rows Number of rows (default 5)
         * @param {number} cols Number of columns (default 6)
         * @returns {string} HTML string of <tr> elements
         */
        renderTableRows: function (rows = 5, cols = 6) {
            let html = '';
            const widths = ['8%', '22%', '18%', '16%', '14%', '12%', '10%'];
            for (let r = 0; r < rows; r++) {
                html += '<tr class="miki-skeleton-table-row">';
                for (let c = 0; c < cols; c++) {
                    const w = widths[c % widths.length];
                    if (c === 0) {
                        html += `
                            <td style="width: 60px;">
                                <div class="miki-skeleton-bar" style="width: 28px; height: 28px; border-radius: 8px;"></div>
                            </td>
                        `;
                    } else if (c === 1) {
                        html += `
                            <td>
                                <div class="d-flex align-items-center gap-2">
                                    <div class="miki-skeleton-box circle-sm" style="width: 34px; height: 34px; flex-shrink: 0;"></div>
                                    <div class="d-flex flex-column gap-1 w-100">
                                        <div class="miki-skeleton-bar" style="width: 75%; height: 15px;"></div>
                                        <div class="miki-skeleton-bar" style="width: 45%; height: 12px;"></div>
                                    </div>
                                </div>
                            </td>
                        `;
                    } else if (c === cols - 1) {
                        html += `
                            <td class="text-center">
                                <div class="d-flex justify-content-center gap-1">
                                    <div class="miki-skeleton-bar" style="width: 30px; height: 30px; border-radius: 6px;"></div>
                                    <div class="miki-skeleton-bar" style="width: 30px; height: 30px; border-radius: 6px;"></div>
                                </div>
                            </td>
                        `;
                    } else {
                        html += `
                            <td>
                                <div class="miki-skeleton-bar" style="width: ${w}; min-width: 60px; height: 16px;"></div>
                            </td>
                        `;
                    }
                }
                html += '</tr>';
            }
            return html;
        },

        /**
         * Renders a full card containing a shimmering table with search bar and pagination
         * @param {number} rows Number of rows
         * @param {number} cols Number of columns
         * @returns {string} HTML string
         */
        renderTableSkeleton: function (rows = 5, cols = 5) {
            return `
                <div class="miki-skeleton-card main-table-card p-3">
                    <div class="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3 pb-2 border-bottom border-light">
                        <div class="d-flex gap-2">
                            <div class="miki-skeleton-bar miki-skeleton-tab active"></div>
                            <div class="miki-skeleton-bar miki-skeleton-tab"></div>
                            <div class="miki-skeleton-bar miki-skeleton-tab"></div>
                        </div>
                        <div class="d-flex gap-2">
                            <div class="miki-skeleton-bar" style="width: 220px; height: 36px; border-radius: 20px;"></div>
                            <div class="miki-skeleton-bar" style="width: 100px; height: 36px; border-radius: 20px;"></div>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table mb-0 align-middle">
                            <tbody>
                                ${this.renderTableRows(rows, cols)}
                            </tbody>
                        </table>
                    </div>
                    <div class="d-flex justify-content-between align-items-center mt-3 pt-2 border-top border-light">
                        <div class="miki-skeleton-bar" style="width: 160px; height: 16px;"></div>
                        <div class="d-flex gap-1">
                            <div class="miki-skeleton-bar" style="width: 30px; height: 30px; border-radius: 6px;"></div>
                            <div class="miki-skeleton-bar" style="width: 30px; height: 30px; border-radius: 6px;"></div>
                            <div class="miki-skeleton-bar" style="width: 30px; height: 30px; border-radius: 6px;"></div>
                        </div>
                    </div>
                </div>
            `;
        },

        /**
         * Renders a list of item card skeletons (e.g., Guardians directory, Activity logs)
         * @param {number} count Number of items (default 4)
         * @returns {string} HTML string
         */
        renderListSkeleton: function (count = 4) {
            let html = '<div class="d-flex flex-column gap-2">';
            for (let i = 0; i < count; i++) {
                html += `
                    <div class="miki-skeleton-list-item">
                        <div class="miki-skeleton-box circle-sm" style="width: 44px; height: 44px; flex-shrink: 0;"></div>
                        <div class="d-flex flex-column gap-2 w-100" style="max-width: 300px;">
                            <div class="miki-skeleton-bar" style="width: 70%; height: 16px;"></div>
                            <div class="miki-skeleton-bar" style="width: 50%; height: 12px;"></div>
                        </div>
                        <div class="d-flex flex-wrap gap-2 ms-auto align-items-center">
                            <div class="miki-skeleton-bar" style="width: 90px; height: 26px; border-radius: 14px;"></div>
                            <div class="miki-skeleton-bar" style="width: 90px; height: 26px; border-radius: 14px;"></div>
                        </div>
                        <div class="d-flex gap-1 ms-3">
                            <div class="miki-skeleton-bar" style="width: 32px; height: 32px; border-radius: 8px;"></div>
                        </div>
                    </div>
                `;
            }
            html += '</div>';
            return html;
        },

        /**
         * Renders a chart skeleton placeholder with simulated visual bars
         * @param {number} height Height in pixels
         * @returns {string} HTML string
         */
        renderChartSkeleton: function (height = 280) {
            return `
                <div class="miki-skeleton-card p-4">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <div class="miki-skeleton-bar" style="width: 160px; height: 20px;"></div>
                        <div class="miki-skeleton-bar" style="width: 90px; height: 28px; border-radius: 14px;"></div>
                    </div>
                    <div class="d-flex align-items-end justify-content-between gap-2" style="height: ${height}px; padding: 20px 10px;">
                        <div class="miki-skeleton-bar" style="width: 10%; height: 45%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 75%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 30%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 90%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 60%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 80%; border-radius: 6px 6px 0 0;"></div>
                        <div class="miki-skeleton-bar" style="width: 10%; height: 50%; border-radius: 6px 6px 0 0;"></div>
                    </div>
                </div>
            `;
        },

        /**
         * Renders a polite and branded empty state component
         * @param {object} opts Options { icon, title, message, actionText, actionCallback }
         * @returns {string} HTML string
         */
        renderEmptyState: function (opts = {}) {
            const icon = opts.icon || '&#128269;';
            const title = opts.title || 'No Records Found';
            const message = opts.message || 'There are no items to display matching your criteria.';
            let actionBtn = '';
            if (opts.actionText && opts.actionCallback) {
                actionBtn = `<button class="btn btn-primary rounded-pill px-4 shadow-sm" onclick="${opts.actionCallback}">${opts.actionText}</button>`;
            }
            return `
                <div class="miki-empty-state">
                    <div class="miki-state-icon-wrap">${icon}</div>
                    <h5 class="miki-state-title">${title}</h5>
                    <p class="miki-state-desc">${message}</p>
                    ${actionBtn}
                </div>
            `;
        },

        /**
         * Renders a friendly error state component with a retry button
         * @param {object} opts Options { title, message, retryCallback }
         * @returns {string} HTML string
         */
        renderErrorState: function (opts = {}) {
            const title = opts.title || 'Failed to Load Data';
            const message = opts.message || 'An error occurred while connecting to the server. Please try again.';
            const retryCallback = opts.retryCallback || 'location.reload()';
            return `
                <div class="miki-error-state">
                    <div class="miki-state-icon-wrap">&#9888;&#65039;</div>
                    <h5 class="miki-state-title text-danger">${title}</h5>
                    <p class="miki-state-desc">${message}</p>
                    <button class="btn btn-outline-danger rounded-pill px-4" onclick="${retryCallback}">
                        <i class="fa fa-refresh me-1"></i> Retry
                    </button>
                </div>
            `;
        },

        /**
         * Shows the top navigation progress bar for instant feedback
         */
        showProgressBar: function () {
            let bar = document.getElementById('miki-top-progress-bar');
            if (!bar) {
                bar = document.createElement('div');
                bar.id = 'miki-top-progress-bar';
                document.body.appendChild(bar);
            }
            bar.style.opacity = '1';
            bar.style.width = '30%';
            setTimeout(() => {
                if (bar && bar.style.opacity === '1') bar.style.width = '75%';
            }, 150);
        },

        /**
         * Completes and hides the top progress bar
         */
        hideProgressBar: function () {
            const bar = document.getElementById('miki-top-progress-bar');
            if (!bar) return;
            bar.style.width = '100%';
            setTimeout(() => {
                bar.style.opacity = '0';
                setTimeout(() => {
                    bar.style.width = '0%';
                }, 250);
            }, 200);
        },

        /**
         * Fades out and cleans up the initial page skeleton loader
         */
        hidePageLoader: function () {
            const loaders = document.querySelectorAll('.loader-wrapper');
            loaders.forEach(l => {
                l.style.transition = 'opacity 0.35s ease, visibility 0.35s ease';
                l.style.opacity = '0';
                setTimeout(() => {
                    if (l && l.parentNode) {
                        l.style.display = 'none';
                        l.parentNode.removeChild(l);
                    }
                }, 350);
            });
            this.hideProgressBar();
        },

        /**
         * Intercepts sidebar / menu clicks for smooth progress bar transition (prevents white flashes)
         */
        initModuleTransitions: function () {
            document.addEventListener('click', function (e) {
                const link = e.target.closest('a');
                if (!link) return;
                const href = link.getAttribute('href');
                if (!href || href.startsWith('#') || href.startsWith('javascript') || href.startsWith('mailto')) return;
                if (link.target === '_blank') return;

                // Internal admin navigation: show top progress bar
                if (href.startsWith('/admin-panel') || href.startsWith('/')) {
                    MikiSkeleton.showProgressBar();
                }
            });
        }
    };

    // Attach to global window object
    window.MikiSkeleton = MikiSkeleton;

    // Initialize module transitions on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            MikiSkeleton.initModuleTransitions();
        });
    } else {
        MikiSkeleton.initModuleTransitions();
    }

    // Automatically hide page loader on full load
    window.addEventListener('load', function () {
        setTimeout(function () {
            MikiSkeleton.hidePageLoader();
        }, 150);
    });

})(window, document);

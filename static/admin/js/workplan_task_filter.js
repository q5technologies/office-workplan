(function initFilter() {
    // Wait until django.jQuery is fully available in the DOM
    if (typeof django === 'undefined' || !django.jQuery) {
        setTimeout(initFilter, 50);
        return;
    }

    const $ = django.jQuery;

    $(document).ready(function() {
        const $ownerSelect = $('#id_owner');

        function filterTasks() {
            const ownerId = $ownerSelect.val();
            const ownerMarker = `[owner_id:${ownerId}]`;

            // Matches inline dropdowns ending in '-task' (e.g. id_activities-0-task)
            $('select[id$="-task"]').each(function() {
                const $select = $(this);

                $select.find('option').each(function() {
                    const $option = $(this);
                    if (!$option.val()) return; // Preserve the blank '---------' option

                    // 1. Cache the raw label containing the marker
                    if (!$option.data('original-text')) {
                        $option.data('original-text', $option.text());
                    }

                    const originalText = $option.data('original-text');

                    // 2. Clean the UI label by stripping [owner_id:X]
                    const cleanText = originalText.replace(/\s*\[owner_id:\d+\]/, '');
                    $option.text(cleanText);

                    // 3. Filter dropdown options based on selected Workplan owner
                    if (ownerId && originalText.includes(ownerMarker)) {
                        $option.prop('disabled', false).show();
                    } else {
                        $option.prop('disabled', true).hide();
                    }
                });

                // Reset selection if the currently selected option was disabled
                const $selected = $select.find('option:selected');
                if ($selected.length && $selected.prop('disabled')) {
                    $select.val('');
                }
            });
        }

        if ($ownerSelect.length) {
            filterTasks();
            $ownerSelect.on('change', filterTasks);

            // Re-apply filter when new inline rows are added dynamically
            $(document).on('formset:added', function() {
                filterTasks();
            });
        }
    });
})();
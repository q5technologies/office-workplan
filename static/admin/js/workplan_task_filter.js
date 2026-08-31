(function initFilter() {
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

            $('select[id$="-task"]').each(function() {
                const $select = $(this);
                
                // 1. On first run, cache the original full list of options in memory
                if (!$select.data('all-options')) {
                    const allOptions = $select.find('option').map(function() {
                        const $opt = $(this);
                        return {
                            val: $opt.val(),
                            originalText: $opt.text(),
                            cleanText: $opt.text().replace(/\s*\[owner_id:\d+\]/, ''),
                            isBlank: !$opt.val()
                        };
                    }).get();
                    $select.data('all-options', allOptions);
                }

                // 2. Remember current selection
                const currentVal = $select.val();
                const allOptions = $select.data('all-options');
                
                // 3. Clear the DOM dropdown completely
                $select.empty();

                // 4. Rebuild the UI with ONLY matching options (and the blank default)
                let valueStillValid = false;
                
                $.each(allOptions, function(i, opt) {
                    if (opt.isBlank || (ownerId && opt.originalText.includes(ownerMarker))) {
                        $select.append($('<option></option>').val(opt.val).text(opt.cleanText));
                        if (currentVal === opt.val) {
                            valueStillValid = true;
                        }
                    }
                });

                // 5. Restore previous selection if it survives the filter, otherwise reset
                if (valueStillValid) {
                    $select.val(currentVal);
                } else {
                    $select.val('');
                }
            });
        }

        if ($ownerSelect.length) {
            filterTasks();
            $ownerSelect.on('change', filterTasks);

            // Applies filter cleanly to newly added inline rows
            $(document).on('formset:added', function() {
                filterTasks();
            });
        }
    });
})();
if (typeof django !== 'undefined' && django.jQuery) {
    (function($) {
        $(document).ready(function() {
            const $ownerSelect = $('#id_owner');
            
            function filterTasks() {
                const ownerId = $ownerSelect.val();
                const ownerMarker = `[owner_id:${ownerId}]`;

                $('select[id$="-task"]').each(function() {
                    const $select = $(this);
                    
                    $select.find('option').each(function() {
                        const $option = $(this);
                        if (!$option.val()) return; // Keep the '---------' option

                        // 1. Cache the original text with the ID marker
                        if (!$option.data('original-text')) {
                            $option.data('original-text', $option.text());
                            // Clean up the UI so the user doesn't see [owner_id:X]
                            $option.text($option.text().replace(/ \[owner_id:\d+\]/, ''));
                        }

                        const originalText = $option.data('original-text');

                        // 2. Show/Hide based on the selected owner
                        if (ownerId && originalText.includes(ownerMarker)) {
                            $option.show().prop('disabled', false).removeAttr('hidden');
                        } else {
                            $option.hide().prop('disabled', true).attr('hidden', 'hidden');
                        }
                    });

                    // 3. Reset the selection if the currently selected option was just hidden
                    const $selected = $select.find('option:selected');
                    if ($selected.length && $selected.attr('hidden')) {
                        $select.val('');
                    }
                });
            }

            // Initialize if the owner field exists on this page
            if ($ownerSelect.length) {
                // Filter on initial page load
                filterTasks();
                
                // Filter whenever the owner dropdown is changed
                $ownerSelect.on('change', filterTasks);

                // CRITICAL: Re-run the filter when a new inline row is added dynamically
                $(document).on('formset:added', function(event, $row, formsetName) {
                    filterTasks();
                });
            }
        });
    })(django.jQuery);
}
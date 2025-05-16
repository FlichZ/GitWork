document.addEventListener('DOMContentLoaded', function() {
    const dropdowns = document.querySelectorAll('.dropdown');
    dropdowns.forEach(dropdown => {
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        toggle.addEventListener('click', function() {
            menu.hidden = !menu.hidden;
        });
        document.addEventListener('click', function(event) {
            if (!dropdown.contains(event.target)) {
                menu.hidden = true;
            }
        });
    });
});